import os, sys
from pathlib import Path
from datetime import datetime
import zipfile
import platform, psutil
import logging

# Only import subprocess on non-Windows platforms
# Windows uses os.startfile instead
if sys.platform != "win32":
    import subprocess

# Import PySide6 Modules
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QMessageBox, QLabel, QPushButton
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer

# Import custom modules
from utils import FileUtils, AppLogger

from .widgets import SnippetEditor
from .menus import *
from .service import *

# Setup logging
logger = logging.getLogger(__name__)



class QSnippet(QMainWindow):
    def __init__(self, parent=None) -> None:
        """
        Initialize the main QSnippet application window.

        Configures window properties, application metadata, initializes the
        snippet service, sets up UI components (editor, menus, toolbar, tray),
        and starts the background service.

        Args:
            parent (Any): Optional parent object providing configuration and
                application references.

        Returns:
            None
        """
        logger.info("Initializing QSnippet Main Window")
        
        super().__init__()
        self.parent = parent
        self.cfg = parent.cfg
        self.app = parent.app
        self.state = "stopped"

        self.setWindowTitle(self.parent.program_name)
        self.setWindowIcon(QIcon(self.parent.images["icon"]))

        # Set application-level metadata
        # This fixes app icon missing on linux taskbar
        self.app.setWindowIcon(QIcon(self.parent.images["icon"]))
        self.app.setApplicationName(self.parent.program_name)
        self.app.setDesktopFileName(self.parent.program_name)

        width = self.parent.dimensions_windows["main"]["width"]
        height = self.parent.dimensions_windows["main"]["height"]
        self.resize(width, height)
        logger.debug("Window dimensions set: %sx%s", width, height)

        self.snippet_service = SnippetService(
            self.parent.snippet_db_file,
            settings_provider=lambda: self.parent.settings,
        )

        self.initUI()
        self.init_menubar()
        self.init_toolbar()
        self.init_tray_menu()
        self.start_service()

        logger.info("QSnippet Main Window initialized successfully")

    def initUI(self) -> None:
        """
        Initialize the main editor UI.

        Creates the central widget layout, conditionally displays a Linux
        compatibility notice, initializes the snippet editor, and optionally
        shows the window at startup based on settings.

        Returns:
            None
        """
        logger.info("Initializing main UI")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Linux only notice with close button and GitHub issue link
        notice_text = (
            "Linux compatibility is currently limited. "
            "<a href=\"https://github.com/queball1999/QSnippet/issues/new?title=Linux+Issue&body=Please+describe+the+issue\">"
            "Report a bug</a> or <a href=\"https://github.com/queball1999/QSnippet/issues\">view existing issues</a>."
        )

        # Create a container widget for the notice
        notice_container = QWidget()
        notice_layout = QHBoxLayout(notice_container)
        notice_layout.setContentsMargins(10, 5, 5, 5)

        # Create the notice label with HTML
        self.linux_notice_label = QLabel(notice_text)
        self.linux_notice_label.setAlignment(Qt.AlignCenter)
        self.linux_notice_label.setOpenExternalLinks(True)

        # Create close button
        close_button = QPushButton("✕")
        close_button.setMaximumWidth(30)
        close_button.setToolTip("Dismiss notice")
        close_button.clicked.connect(notice_container.hide)

        # Add widgets to layout
        notice_layout.addWidget(self.linux_notice_label, 1)
        notice_layout.addWidget(close_button)
        notice_container.setLayout(notice_layout)

        # Style the notice container
        notice_container.setStyleSheet("""
            QWidget {
                padding: 5px;
                background: #ffcc00;
                color: #000000;
            }
            QLabel {
                background: transparent;
                color: #000000;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #000000;
                padding: 0px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }
        """)

        self.linux_notice = notice_container
        self.linux_notice.hide()
        if sys.platform.startswith("linux"):
            self.linux_notice.show()

        # Show editor at startup
        self.editor = SnippetEditor(config_path=self.parent.snippet_db_file, main=self.parent, parent=self)
        self.editor.trigger_reload.connect(lambda: self.snippet_service.refresh())
        
        layout.addWidget(self.linux_notice)
        layout.addWidget(self.editor)
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Check if we need to show UI at start
        # Default to true if setting missing
        # If skipped, we load later when opening UI.
        if self.parent.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", True):
            logger.debug("Showing UI at startup")
            self.show()

    def init_menubar(self) -> None:
        """
        Initialize the application menu bar and connect actions.

        Creates the menu bar, connects its signals to handler methods,
        and sets it on the main window.

        Returns:
            None
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
        self.menubar.showPlaceholderManager.connect(self.show_placeholder_manager)
        self.setMenuBar(self.menubar)

        # Populate any already-saved custom placeholders into the menu
        self.refresh_placeholder_integrations()

    def init_toolbar(self) -> None:
        """
        Initialize the application toolbar.

        Creates the toolbar and adds it to the main window.

        Returns:
            None
        """
        logger.info("Initializing toolbar")

        self.toolbar = ToolbarMenu(self)
        self.addToolBar(self.toolbar)

    def init_tray_menu(self) -> None:
        """
        Initialize the application toolbar.

        Creates the toolbar and adds it to the main window.

        Returns:
            None
        """
        logger.info("Initializing system tray menu")

        try:
            icon_path = self.parent.images.get("icon")
            
            # Fix icon for windows os
            if sys.platform == "win32":
                icon_path = self.parent.images.get("win_icon")

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

    def run(self) -> None:
        """
        Run the Qt application event loop.

        Returns:
            None

        Raises:
            SystemExit: Always raised when the Qt event loop exits.
        """
        logger.info("Starting Qt application event loop")
        sys.exit(self.app.exec())

    # Serivce Control

    def start_service(self) -> None:
        """
        Start the snippet service and update application state.

        Returns:
            None
        """
        logger.info("Starting snippet service")
        self.snippet_service.start()
        self.state = "running"
        self.update_status_bar("Running")

    def stop_service(self) -> None:
        """
        Stop the snippet service and update application state.

        Returns:
            None
        """
        logger.info("Stopping snippet service")
        self.snippet_service.stop()
        self.state = "stopped"
        self.update_status_bar("Stopped")

    def pause_service(self) -> None:
        """
        Pause the snippet service and update application state.

        Returns:
            None
        """
        logger.info("Pausing snippet service")
        self.snippet_service.pause()
        self.state = "paused"
        self.update_status_bar("Paused")

    def resume_service(self) -> None:
        """
        Resume the snippet service and update application state.

        Returns:
            None
        """
        logger.info("Resuming snippet service")
        self.snippet_service.resume()
        self.state = "running"
        self.update_status_bar("Running")

    def check_service_status(self) -> None:
        """
        Update the status bar based on the current service state.

        Returns:
            None
        """
        logger.debug("Checking service status")

        if self.snippet_service.active():
            self.update_status_bar("Running")
        elif self.state == "paused":
            self.update_status_bar("Paused")
        elif self.state == "stopped":
            self.update_status_bar("Stopped")
        else:
            self.update_status_bar("Error")

    def update_status_bar(self, status: str) -> None:
        """
        Update the status bar message when the editor is visible.

        Args:
            status (str): The service status string to display.

        Returns:
            None
        """
        try:
            if self.editor.isVisible():
                self.statusBar().showMessage(f"Service status: {status}")
        except Exception as e:
            logger.exception(f"Failed to update status bar: {e}")

    # Handlers
    def handle_startup_signal(self, enabled: bool) -> None:
        """
        Enable or disable startup at boot and persist the setting.

        Updates platform-specific autostart configuration and writes the
        updated preference to the settings file.

        Args:
            enabled (bool): Whether startup at boot should be enabled.

        Returns:
            None
        """
        logger.info("Updating startup setting: %s", enabled)
        
        try:
            if sys.platform == "win32":
                from utils.reg_utils import RegUtils

                if enabled:
                    RegUtils.add_to_run_key(
                        app_exe_path=self.parent.app_exe,
                        entry_name="QSnippet",
                    )
                else:
                    RegUtils.remove_from_run_key(entry_name="QSnippet")

            elif sys.platform.startswith("linux") is not None:
                from utils.linux_utils import LinuxUtils

                if enabled:
                    LinuxUtils.enable_autostart()
                else:
                    LinuxUtils.disable_autostart()
                    
            else:
                logger.info("Cannot process auto-start change. This operating system is currently unsupported.")
                return
            
            self.parent.skip_reg = False
            self.parent.settings["general"]["startup_behavior"]["start_at_boot"]["value"] = enabled
            FileUtils.write_yaml(
                self.parent.settings_file,
                self.parent.settings,
            )

            QTimer.singleShot(1000, self.unset_skip_reg)

        except Exception:
            logger.exception("Failed to update startup setting")

    def handle_show_ui_signal(self, checked: bool) -> None:
        """
        Persist the show UI at startup preference.

        Args:
            checked (bool): Whether the UI should be shown at application start.

        Returns:
            None
        """
        logger.info("Updating show UI at startup: %s", checked)

        self.parent.settings["general"]["startup_behavior"]["show_ui_at_start"]["value"] = checked
        FileUtils.write_yaml(
            self.parent.settings_file,
            self.parent.settings,
        )

    def handle_import_action(self) -> None:
        """
        Import snippets via dialog and refresh service and UI.

        Returns:
            None
        """
        logger.info("Importing snippets via menu action")

        FileUtils.import_snippets_with_dialog(
            self,
            self.parent.snippet_db,
        )
        self.snippet_service.refresh()
        self.editor.load_snippets()

    def handle_export_action(self) -> None:
        """
        Export snippets via dialog and refresh service and UI.

        Returns:
            None
        """
        logger.info("Exporting snippets via menu action")

        FileUtils.export_snippets_with_dialog(
            self,
            self.parent.snippet_db,
        )
        self.snippet_service.refresh()
        self.editor.load_snippets()

    def handle_rename_action(self) -> None:
        """
        Handle the rename action triggered by the menu.

        Invokes the editor rename action handler and logs failures.

        Returns:
            None
        """
        logger.info("Rename action triggered")
        try:
            self.editor.handle_rename_action()
        except Exception as e:
            logger.exception(f"Failed to emit rename action signal: {e}")

    def handle_collect_logs(self) -> None:
        """
        Collect logs and configuration files into a ZIP archive.

        Writes log files and configuration files to a timestamped archive in the
        user's Downloads directory and optionally opens the folder on completion.

        Returns:
            None
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

    def handle_log_level(self, level: str) -> None:
        """
        Update application log level and persist to configuration.

        Updates the root logger level, saves the selected log level to the
        configuration file, and reinitializes the application logger.

        Args:
            level (str): The log level name to apply.

        Returns:
            None
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

    def handle_show_info(self) -> None:
        """
        Display the About dialog.

        Builds application information and shows it in a Qt message box.

        Returns:
            None
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

    def build_about_info(self) -> dict | bool:
        """
        Build application "About" information.

        Generates HTML and plain text representations including build info,
        support contacts, key file paths, runtime environment details, and
        system resource information.

        Returns:
            dict | bool: A dictionary with "html" and "text" keys on success,
                or False on failure.
        """
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
        
    def show_placeholder_manager(self) -> None:
        """
        Show the placeholder manager dialog.

        Lets users add, edit, or delete user-defined placeholders.
        Refreshes the menu and intellisense after any change.

        Returns:
            None
        """
        logger.info("Showing placeholder manager")

        from ui.widgets.placeholder_dialog import PlaceholderDialog

        self.placeholder_dialog = PlaceholderDialog(
            snippet_db=self.parent.snippet_db,
            parent=self,
        )
        self.placeholder_dialog.placeholders_updated.connect(self.refresh_placeholder_integrations)
        self.placeholder_dialog.exec()

    def refresh_placeholder_integrations(self) -> None:
        """
        Synchronise the Custom placeholder menu, snippet-form intellisense,
        and the SnippetExpander's cached custom placeholders with the current
        state of the database.

        Returns:
            None
        """
        logger.debug("Refreshing placeholder integrations")
        try:
            placeholders = self.parent.snippet_db.get_all_custom_placeholders()
            self.menubar.rebuild_custom_placeholder_menu(placeholders)
            self.editor.form.fill_intellisense_popup_list()
            # Reload the expander cache so expansions pick up the latest values
            self.snippet_service.refresh()
        except Exception:
            logger.warning("Failed to refresh placeholder integrations", exc_info=True)

    def show_settings_window(self) -> None:
        """
        Show the settings window dialog.

        Returns:
            None
        """
        logger.info("Showing settings window")

        from ui.widgets.settings import SettingsDialog

        self.settings_dialog = SettingsDialog(
            settings=self.parent.settings,
            save_callback=self.save_settings,
            parent=self,
        )
        self.settings_dialog.exec()

    def save_settings(self, settings: dict) -> None:
        """
        Save current settings to file.

        Updates the in-memory settings reference and writes the settings
        to the settings YAML file.

        Args:
            settings (dict): The updated settings dictionary to persist.

        Returns:
            None
        """
        logger.info("Saving settings to file")

        # Update parent reference in memory
        self.parent.settings = settings

        FileUtils.write_yaml(
            self.parent.settings_file,
            self.parent.settings,
        )

        # Refresh the tray settings
        self.tray.contextMenu().refresh()

    def unset_skip_reg(self):
        """
        Reset the registry skip flag.

        Returns:
            None
        """
        logger.debug("Resetting skip_reg flag")
        self.parent.skip_reg = False

    def on_tray_icon_activated(self, event) -> None:
        """
        Handle system tray icon activation events.

        Shows or focuses the main window when the tray icon is triggered.

        Args:
            event (Any): The tray activation event value.

        Returns:
            None
        """
        if event == QSystemTrayIcon.Trigger:
            if not self.isVisible():
                self.show_window()
            else:
                self.raise_()
                self.activateWindow()

    def show_window(self) -> None:
        """
        Show the main application window and trigger notice checks.

        Returns:
            None
        """
        logger.info("Showing main window")
        self.show()
        QTimer.singleShot(500, self.parent.check_notices)

    def exit(self) -> None:
        """
        Exit the application cleanly.

        Stops the snippet service, clears managed clipboard data, closes
        database connections, hides the tray icon, and exits the process.

        Returns:
            None

        Raises:
            SystemExit: Always raised when exiting the application.
        """
        logger.info("Exiting QSnippet")
        self.snippet_service.shutdown()
        self.parent.snippet_db.close()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event) -> None:
        """
        Handle window close events by hiding the window.

        Overrides the default close behavior to ignore the event and hide the
        window instead of quitting.

        Args:
            event (Any): The Qt close event.

        Returns:
            None
        """
        logger.debug("Close event intercepted; hiding window")
        event.ignore()
        self.hide()