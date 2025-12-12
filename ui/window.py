import os, sys
from pathlib import Path
from datetime import datetime
import zipfile
import platform, psutil

from PySide6.QtWidgets import (
    QSystemTrayIcon, QMainWindow, QHBoxLayout, QWidget,
    QMessageBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer

from utils import FileUtils, RegUtils, AppLogger
from .widgets import SnippetEditor
from .menus import *
from .service import *
import logging

logger = logging.getLogger(__name__)

class QSnippet(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.cfg = parent.cfg
        self.app = parent.app
        self.state = "stopped"

        self.setWindowTitle(self.parent.program_name)
        self.setWindowIcon(QIcon(self.parent.images["icon"]))

        width = self.parent.dimensions_windows["main"]["width"]
        height = self.parent.dimensions_windows["main"]["height"]
        self.resize(width, height)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.check_service_status)
        # commentiung out 09/04/25
        # self._status_timer.start(5000)

        self.snippet_service = SnippetService(self.parent.snippet_db_file)

        self.initUI()
        self.init_menubar()
        self.init_toolbar()
        self.init_tray_menu()
        self.start_service()

    def initUI(self):
        container = QWidget()
        layout = QHBoxLayout(container)

        # Show editor at startup
        self.editor = SnippetEditor(config_path=self.parent.snippet_db_file, main=self.parent, parent=self)
        self.editor.trigger_reload.connect(lambda: self.snippet_service.refresh())
        
        layout.addWidget(self.editor)
        container.setLayout(layout)
        self.setCentralWidget(container)
        if self.parent.general_show_ui_at_start:
            self.show()

    def init_menubar(self):
        self.menubar = MenuBar(main=self.parent, parent=self)
        self.menubar.importAction.connect(self.handle_import_action)
        self.menubar.exportAction.connect(self.handle_export_action)
        self.menubar.collectLogsRequested.connect(self.handle_collect_logs)
        self.menubar.logLevelChanged.connect(self.handle_log_level)
        self.menubar.showAppInfo.connect(self.handle_show_info)
        self.setMenuBar(self.menubar)

    def init_toolbar(self):
        # install the toolbar
        self.toolbar = ToolbarMenu(self)
        self.addToolBar(self.toolbar)

    def init_tray_menu(self):
        logger = logging.getLogger(__name__)
        logger.debug("init_tray_menu: starting initialization of system tray")

        try:
            icon_path = None
            try:
                icon_path = self.parent.images.get("icon")
                logger.debug("init_tray_menu: icon path resolved: %s", icon_path)
            except Exception:
                logger.exception("init_tray_menu: failed to read icon path from parent.images")

            icon = QIcon(icon_path)
            logger.debug("init_tray_menu: QIcon created (isNull=%s)", icon.isNull())

            self.tray = QSystemTrayIcon(icon, self.app)
            self.tray.setToolTip('QSnippet')
            logger.debug("init_tray_menu: QSystemTrayIcon created and tooltip set")

            # Allow left clicks of tray icon to show UI
            self.tray.activated.connect(self.on_tray_icon_activated)
            logger.debug("init_tray_menu: connected activated -> on_tray_icon_activated")

            menu = TrayMenu(main=self.parent)
            logger.debug("init_tray_menu: TrayMenu instance created")

            # Connect menu signals with logging for each connection
            menu.edit_signal.connect(self.show_window)
            logger.debug("init_tray_menu: connected edit_signal -> show_window")

            menu.exit_signal.connect(self.exit)
            logger.debug("init_tray_menu: connected exit_signal -> exit")

            menu.startup_signal.connect(self.handle_startup_signal)
            logger.debug("init_tray_menu: connected startup_signal -> handle_startup_signal")

            menu.showui_signal.connect(self.handle_show_ui_signal)
            logger.debug("init_tray_menu: connected showui_signal -> handle_show_ui_signal")

            self.tray.setContextMenu(menu)
            logger.debug("init_tray_menu: context menu set on tray")

            self.tray.show()
            logger.info("init_tray_menu: system tray icon shown successfully")
        except Exception:
            logger.exception("init_tray_menu: unexpected error while initializing system tray")

    def run(self):
        sys.exit(self.app.exec())

    def start_service(self):
        self.snippet_service.start()
        self.state = "running"
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Running")

    def stop_service(self):
        self.snippet_service.stop()
        self.state = "stopped"
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Stopped")

    def pause_service(self):
        self.snippet_service.pause()
        self.state = "paused"
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Paused")

    def resume_service(self):
        self.snippet_service.resume()
        self.state = "running"
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Running")

    def check_service_status(self):
        if self.snippet_service._thread.is_alive() and self.state == "running":
            self.statusBar().showMessage(f"Service status: Running")
        elif self.state == "paused":
            self.statusBar().showMessage(f"Service status: Paused")
        elif self.state == "stopped":
            self.statusBar().showMessage(f"Service status: Stopped")
        else:   # default to error message
            self.statusBar().showMessage(f"Service status: Error")

    def handle_startup_signal(self, enabled: bool):
        if enabled:
            RegUtils.add_to_run_key(app_exe_path=self.parent.app_exe, entry_name="QSnippet")
        else:
            RegUtils.remove_from_run_key(entry_name="QSnippet")

        # Update YAML settings
        self.parent.skip_reg = False    # Force a skip so we only load reg key once
        self.parent.settings["general"]["start_at_boot"] = enabled
        FileUtils.write_yaml(self.parent.settings_file, self.parent.settings)
        QTimer.singleShot(1000, self.unset_skip_reg)

    def handle_show_ui_signal(self, checked: bool):
        self.parent.settings["general"]["show_ui_at_start"] = checked
        FileUtils.write_yaml(self.parent.settings_file, self.parent.settings)

    def handle_import_action(self):
        FileUtils.import_snippets_with_dialog(self, self.parent.snippet_db)
        self.snippet_service.refresh()  # Refresh Snippet Service
        self.editor.load_snippets() # Trigger editor to re-load snippets

    def handle_export_action(self):
        FileUtils.export_snippets_with_dialog(self, self.parent.snippet_db)
        self.snippet_service.refresh()  # Refresh Snippet Service
        self.editor.load_snippets() # Trigger refresh of snippets

    def handle_collect_logs(self):
        """Collect logs and relevant config into a ZIP in Downloads."""
        try:
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"QSnippet_Logs_{timestamp}.zip"
            zip_path = downloads_dir / zip_name

            log_dir = Path(self.parent.logs_dir)
            app_data_dir = Path(self.parent.app_data_dir)
            config_file = Path(self.parent.config_file)
            settings_file = Path(self.parent.settings_file)

            if not log_dir.exists():
                QMessageBox.information(self, "No Logs Found",
                                        "No logs directory exists yet.")
                return

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:

                # Add logs
                for file in log_dir.rglob("*"):
                    if file.is_file():
                        arcname = file.relative_to(log_dir)
                        zipf.write(file, f"logs/{arcname}")

                # Add config files
                zipf.write(config_file, "config/config.yaml")
                zipf.write(settings_file, "config/settings.yaml")
                
                # Add about info
                info = self.build_about_info()
                if info:
                    zipf.writestr("about_info.txt", info["text"])

            reply = QMessageBox.question(
                self,
                "Logs Collected",
                f"Logs exported to:\n\n{zip_path}\n\nOpen folder?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                if sys.platform == "win32":
                    os.startfile(downloads_dir)
                elif sys.platform == "darwin":
                    subprocess.call(["open", downloads_dir])
                else:
                    subprocess.call(["xdg-open", downloads_dir])

        except Exception as e:
            logging.exception("Failed to collect logs")
            QMessageBox.critical(self, "Error Collecting Logs", str(e))
    
    def handle_log_level(self, level: str):
        """Set log level through AppLogger and persist to settings.yaml."""
        try:
            # Convert string → logging constant
            mapping = {
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG
            }

            new_level = mapping.get(level.upper(), logging.ERROR)

            # Update logger immediately
            root = logging.getLogger()
            root.setLevel(new_level)
            logging.info(f"Log level changed to {level}")

            # Update YAML settings
            self.parent.settings["log_level"] = level
            FileUtils.write_yaml(self.parent.settings_file, self.parent.settings)

            # Re-init logger class
            self.parent.logger = AppLogger(
                log_filepath=self.parent.log_path,
                log_level=new_level
            )

        except Exception as e:
            logging.exception("Failed to update log level")
            QMessageBox.critical(self, "Error", f"Failed to set log level:\n{e}")


    def handle_show_info(self):
        info = self.build_about_info()
        if not info:
            QMessageBox.critical(self, "Error", "Unable to load application info.")
            return

        box = QMessageBox(self)
        box.setWindowTitle(f"About {self.parent.program_name}")
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.setText(info["html"])
        box.exec()


    def build_about_info(self):
        """Return dict with 'html' and 'text' fields or False on failure."""
        try:
            parent = self.parent
            name = parent.program_name
            version = getattr(parent, "version", "Unknown")

            support_email = parent.support_info.get("email", "N/A")
            support_site = parent.support_info.get("site", "N/A")

            # File paths
            config_file = Path(parent.config_file)
            settings_file = Path(parent.settings_file)
            log_dir = Path(parent.logs_dir)

            # Install date
            try:
                install_ts = config_file.stat().st_ctime
                install_date = datetime.fromtimestamp(install_ts).strftime("%Y-%m-%d %H:%M")
            except:
                install_date = "Unknown"

            # Log size
            total_log_size = 0
            if log_dir.exists():
                for f in log_dir.rglob("*"):
                    if f.is_file():
                        total_log_size += f.stat().st_size
            log_size_mb = round(total_log_size / (1024*1024), 2)

            # System info
            os_name = platform.system()
            os_version = platform.version()
            cpu_count = psutil.cpu_count(logical=True)
            ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)

            # Bundle mode
            bundled = hasattr(sys, "_MEIPASS")
            bundle_mode = "PyInstaller Bundle" if bundled else "Source / Development"

            # ----- HTML VERSION -----
            html = f"""
            <h2>{name}</h2>
            Version: {version}<br>
            Estimated Install Date: {install_date}<br><br>

            <b>Support Information</b><br>
            Email: <a href="mailto:{support_email}">{support_email}</a><br>
            Website: <a href="{support_site}">{support_site}</a><br><br>

            <b>Application Directories</b><br>
            App Data: <a href="file:///{parent.app_data_dir}">{parent.app_data_dir}</a><br>
            Logs: <a href="file:///{parent.logs_dir}">{parent.logs_dir}</a><br>
            Total Log Size: {log_size_mb} MB<br><br>

            <b>Config Files</b><br>
            Config: <a href="file:///{config_file}">{config_file}</a><br>
            Settings: <a href="file:///{settings_file}">{settings_file}</a><br><br>

            <b>Environment</b><br>
            Runtime Mode: {bundle_mode}<br>
            Python: {platform.python_version()}<br>
            OS: {os_name} ({os_version})<br>
            CPU Cores: {cpu_count}<br>
            RAM: {ram_gb} GB<br>
            """

            # ----- TEXT VERSION (for logs ZIP) -----
            text = (
                f"{name}\n"
                f"Version: {version}\n"
                f"Install Date: {install_date}\n\n"
                f"Support Information\n"
                f"Email: {support_email}\n"
                f"Website: {support_site}\n\n"
                f"Application Directories\n"
                f"App Data: {parent.app_data_dir}\n"
                f"Logs: {parent.logs_dir}\n"
                f"Total Log Size: {log_size_mb} MB\n\n"
                f"Config Files\n"
                f"Config: {config_file}\n"
                f"Settings: {settings_file}\n\n"
                f"Environment\n"
                f"Runtime Mode: {bundle_mode}\n"
                f"Python: {platform.python_version()}\n"
                f"OS: {os_name} ({os_version})\n"
                f"CPU Cores: {cpu_count}\n"
                f"RAM: {ram_gb} GB\n"
            )

            return {"html": html, "text": text}

        except Exception:
            logging.exception("Failed to build about info")
            return False

    def unset_skip_reg(self):
        self.parent.skip_reg = False

    def on_tray_icon_activated(self, event):
        """ Handle left-click event and show UI """
        if event == QSystemTrayIcon.Trigger:
            # Left click
            if not self.isVisible():
                self.show_window()
            else:
                self.raise_()  # bring to front
                self.activateWindow()

    def show_window(self):
        self.show()
        QTimer.singleShot(500, self.parent.check_notices)

    def exit(self):
        self.stop_service()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event):
        # Override close to hide instead of exiting app
        event.ignore()
        self.hide()
