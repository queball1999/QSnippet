import os, sys
from pathlib import Path
from datetime import datetime
import zipfile
import platform, psutil
import logging

# Import PySide6 Modules
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMainWindow, QHBoxLayout, QWidget,
    QMessageBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer

# Import custom modules
from utils import FileUtils, RegUtils, AppLogger
from .widgets import SnippetEditor
from .menus import *
from .service import *

# Setup logging
logger = logging.getLogger(__name__)



class QSnippet(QMainWindow):
    """
    Main application window for QSnippet.
    Handles UI, system tray, service lifecycle,
    and user-facing actions.
    """

    def __init__(self, parent=None):
        logger.info("Initializing QSnippet Main Window")
        
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
        logger.debug("Window dimensions set: %sx%s", width, height)

        self.snippet_service = SnippetService(self.parent.snippet_db_file)

        self.initUI()
        self.init_menubar()
        self.init_toolbar()
        self.init_tray_menu()
        self.start_service()

        logger.info("QSnippet Main Window initialized successfully")

    def initUI(self):
        """
        Initialize the main editor UI.
        """
        logger.info("Initializing main UI")

        container = QWidget()
        layout = QHBoxLayout(container)

        # Show editor at startup
        self.editor = SnippetEditor(config_path=self.parent.snippet_db_file, main=self.parent, parent=self)
        self.editor.trigger_reload.connect(lambda: self.snippet_service.refresh())
        
        layout.addWidget(self.editor)
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Check if we need to show UI at start
        # Default to true if setting missing
        # If skipped, we load later when opening UI.
        if self.parent.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", True):
            logger.debug("Showing UI at startup")
            self.show()

    def init_menubar(self):
        """
        Initialize application menu bar and connect actions.
        """
        logger.info("Initializing menu bar")

        self.menubar = MenuBar(main=self.parent, parent=self)
        self.menubar.importAction.connect(self.handle_import_action)
        self.menubar.exportAction.connect(self.handle_export_action)
        self.menubar.renameAction.connect(self.handle_rename_action)
        self.menubar.collectLogsRequested.connect(self.handle_collect_logs)
        self.menubar.logLevelChanged.connect(self.handle_log_level)
        self.menubar.showAppInfo.connect(self.handle_show_info)
        self.menubar.show_settings.connect(self.show_settings_window)
        self.setMenuBar(self.menubar)

    def init_toolbar(self):
        """
        Initialize toolbar.
        """
        logger.info("Initializing toolbar")

        self.toolbar = ToolbarMenu(self)
        self.addToolBar(self.toolbar)

    def init_tray_menu(self):
        """
        Initialize the system tray icon and context menu.
        """
        logger.info("Initializing system tray menu")

        try:
            icon_path = self.parent.images.get("icon")
            logger.debug("Tray icon path: %s", icon_path)

            icon = QIcon(icon_path)
            logger.debug("Tray icon loaded (isNull=%s)", icon.isNull())

            self.tray = QSystemTrayIcon(icon, self.app)
            self.tray.setToolTip("QSnippet")

            self.tray.activated.connect(self.on_tray_icon_activated)

            menu = TrayMenu(main=self.parent)

            menu.edit_signal.connect(self.show_window)
            menu.exit_signal.connect(self.exit)
            menu.startup_signal.connect(self.handle_startup_signal)
            menu.showui_signal.connect(self.handle_show_ui_signal)

            self.tray.setContextMenu(menu)
            self.tray.show()

            logger.info("System tray initialized successfully")

        except Exception:
            logger.exception("Failed to initialize system tray")

    def run(self):
        """
        Run the Qt application event loop.
        """
        logger.info("Starting Qt application event loop")
        sys.exit(self.app.exec())

    # Serivce Control

    def start_service(self):
        """ Start snippet service. """
        logger.info("Starting snippet service")
        self.snippet_service.start()
        self.state = "running"
        self._update_status_bar("Running")

    def stop_service(self):
        """ Stop snippet service. """
        logger.info("Stopping snippet service")
        self.snippet_service.stop()
        self.state = "stopped"
        self._update_status_bar("Stopped")

    def pause_service(self):
        """ Pause snippet service. """
        logger.info("Pausing snippet service")
        self.snippet_service.pause()
        self.state = "paused"
        self._update_status_bar("Paused")

    def resume_service(self):
        """ Resume snippet service. """
        logger.info("Resuming snippet service")
        self.snippet_service.resume()
        self.state = "running"
        self._update_status_bar("Running")

    def check_service_status(self):
        """
        Update status bar based on service state.
        """
        logger.debug("Checking service status")

        if self.snippet_service.active():
            self._update_status_bar("Running")
        elif self.state == "paused":
            self._update_status_bar("Paused")
        elif self.state == "stopped":
            self._update_status_bar("Stopped")
        else:
            self._update_status_bar("Error")

    def _update_status_bar(self, status: str):
        """ Update the status bar message. """
        try:
            if self.editor.isVisible():
                self.statusBar().showMessage(f"Service status: {status}")
        except Exception as e:
            logger.exception(f"Failed to update status bar: {e}")

    # Handlers
    def handle_startup_signal(self, enabled: bool):
        """
        Enable or disable startup at boot.
        """
        logger.info("Updating startup setting: %s", enabled)

        try:
            if enabled:
                RegUtils.add_to_run_key(
                    app_exe_path=self.parent.app_exe,
                    entry_name="QSnippet",
                )
            else:
                RegUtils.remove_from_run_key(entry_name="QSnippet")

            self.parent.skip_reg = False
            self.parent.settings["general"]["startup_behavior"]["start_at_boot"]["value"] = enabled
            FileUtils.write_yaml(
                self.parent.settings_file,
                self.parent.settings,
            )

            QTimer.singleShot(1000, self.unset_skip_reg)

        except Exception:
            logger.exception("Failed to update startup setting")

    def handle_show_ui_signal(self, checked: bool):
        """
        Persist show UI at startup preference.
        """
        logger.info("Updating show UI at startup: %s", checked)

        self.parent.settings["general"]["startup_behavior"]["show_ui_at_start"]["value"] = checked
        FileUtils.write_yaml(
            self.parent.settings_file,
            self.parent.settings,
        )

    def handle_import_action(self):
        """
        Import snippets via dialog and refresh UI.
        """
        logger.info("Importing snippets via menu action")

        FileUtils.import_snippets_with_dialog(
            self,
            self.parent.snippet_db,
        )
        self.snippet_service.refresh()
        self.editor.load_snippets()

    def handle_export_action(self):
        """
        Export snippets via dialog.
        """
        logger.info("Exporting snippets via menu action")

        FileUtils.export_snippets_with_dialog(
            self,
            self.parent.snippet_db,
        )
        self.snippet_service.refresh()
        self.editor.load_snippets()

    def handle_rename_action(self):
        """
        Docstring for handle_rename_action
        
        :param self: Description
        """
        logger.info("Rename action triggered")
        try:
            self.editor.handle_rename_action()
        except Exception as e:
            logger.exception(f"Failed to emit rename action signal: {e}")

    def handle_collect_logs(self):
        """
        Collect logs and configuration files into a ZIP archive.
        """
        logger.info("Collecting logs")

        try:
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_path = downloads_dir / f"QSnippet_Logs_{timestamp}.zip"

            log_dir = Path(self.parent.logs_dir)
            config_file = Path(self.parent.config_file)
            settings_file = Path(self.parent.settings_file)

            if not log_dir.exists():
                logger.info("No logs directory found")
                QMessageBox.information(
                    self,
                    "No Logs Found",
                    "No logs directory exists yet.",
                )
                return

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file in log_dir.rglob("*"):
                    if file.is_file():
                        zipf.write(
                            file,
                            f"logs/{file.relative_to(log_dir)}",
                        )

                zipf.write(config_file, "config/config.yaml")
                zipf.write(settings_file, "config/settings.yaml")

                info = self.build_about_info()
                if info:
                    zipf.writestr("about_info.txt", info["text"])

            logger.info("Logs collected: %s", zip_path)

            reply = QMessageBox.question(
                self,
                "Logs Collected",
                f"Logs exported to:\n\n{zip_path}\n\nOpen folder?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                if sys.platform == "win32":
                    os.startfile(downloads_dir)
                elif sys.platform == "darwin":
                    subprocess.call(["open", downloads_dir])
                else:
                    subprocess.call(["xdg-open", downloads_dir])

        except Exception:
            logger.exception("Failed to collect logs")
            QMessageBox.critical(
                self,
                "Error Collecting Logs",
                "An unexpected error occurred while collecting logs.",
            )

    def handle_log_level(self, level: str):
        """
        Update application log level and persist to settings.
        """
        logger.info("Updating log level to %s", level)

        try:
            mapping = {
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG,
            }
            new_level = mapping.get(level.upper(), logging.ERROR)

            root = logging.getLogger()
            root.setLevel(new_level)

            self.parent.cfg["log_level"] = level
            FileUtils.write_yaml(
                self.parent.config_file,
                self.parent.cfg,
            )

            self.parent.logger = AppLogger(
                log_filepath=self.parent.log_path,
                log_level=new_level,
            )

        except Exception:
            logger.exception("Failed to update log level")
            QMessageBox.critical(
                self,
                "Error",
                "Failed to update log level.",
            )

    def handle_show_info(self):
        """
        Display About dialog.
        """
        logger.info("Showing application info dialog")

        info = self.build_about_info()
        if not info:
            QMessageBox.critical(
                self,
                "Error",
                "Unable to load application info.",
            )
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
            # Import build date info
            try:
                from config.build_info import BUILD_VERSION, BUILD_DATE, BUILD_COMMIT
            except ImportError:
                BUILD_VERSION = "unknown"
                BUILD_DATE = "unknown"
                BUILD_COMMIT = "unknown"

            parent = self.parent
            name = parent.program_name

            support_email = parent.support_info.get("email", "N/A")
            support_site = parent.support_info.get("site", "N/A")

            # File paths
            config_file = Path(parent.config_file)
            settings_file = Path(parent.settings_file)
            license_file = Path(parent.license_file)
            log_dir = Path(parent.logs_dir)

            # Install date
            try:
                install_ts = config_file.stat().st_birthtime
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
            Version: {BUILD_VERSION}<br>
            Build Date: {BUILD_DATE}<br>
            Commit: {BUILD_COMMIT}<br>
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
            RAM: {ram_gb} GB<br><br>

            <b>License</b><br>
            GPLv3 © 2026 Queball1999<br>
            License: <a href="file:///{license_file}">{license_file}</a><br><br>
            """

            # ----- TEXT VERSION (for logs ZIP) -----
            text = (
                f"{name}\n"
                f"Version: {BUILD_VERSION}\n"
                f"Build Date: {BUILD_DATE}\n"
                f"Commit: {BUILD_COMMIT}\n"
                f"Estimated Install Date: {install_date}\n\n"
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
        
    def show_settings_window(self):
        """
        Show settings window.
        """
        logger.info("Showing settings window")

        from ui.widgets.settings import SettingsDialog

        self._settings_dialog = SettingsDialog(
            settings=self.parent.settings,
            save_callback=self.save_settings,
            parent=self,
        )
        self._settings_dialog.exec()

    def save_settings(self, settings: dict):
        """
        Save current settings to file.
        """
        logger.info("Saving settings to file")

        # Update parent reference in memory
        self.parent.settings = settings

        FileUtils.write_yaml(
            self.parent.settings_file,
            self.parent.settings,
        )

    def unset_skip_reg(self):
        """
        Reset registry skip flag.
        """
        logger.debug("Resetting skip_reg flag")
        self.parent.skip_reg = False

    def on_tray_icon_activated(self, event):
        """
        Handle tray icon activation.
        """
        if event == QSystemTrayIcon.Trigger:
            if not self.isVisible():
                self.show_window()
            else:
                self.raise_()
                self.activateWindow()

    def show_window(self):
        """
        Show main application window.
        """
        logger.info("Showing main window")
        self.show()
        QTimer.singleShot(500, self.parent.check_notices)

    def exit(self):
        """
        Exit application cleanly.
        """
        logger.info("Exiting QSnippet")
        self.stop_service()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event):
        """
        Override close event to hide window instead of exiting.
        """
        logger.debug("Close event intercepted; hiding window")
        event.ignore()
        self.hide()