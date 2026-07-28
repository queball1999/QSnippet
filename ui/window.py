import os, sys
import html
import threading
from pathlib import Path
from datetime import datetime
import zipfile
import platform
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
from PySide6.QtCore import Qt, QTimer, Signal, QEvent

# Import custom modules
from utils import FileUtils, AppLogger

from .widgets import SnippetEditor
from .menus import *
from .service import *

# Setup logging
logger = logging.getLogger(__name__)



class QSnippet(QMainWindow):
    # Emitted from the pynput background thread; Qt delivers it to the main thread via queued connection.
    vault_trigger_signal = Signal(str, object, str, bool)
    trigger_detected_signal = Signal(str, object)
    dynamic_placeholder_signal = Signal(str, object, str, bool)
    migration_backup_signal = Signal(object, object)

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

        # Live countdown for the "Detected Trigger" status bar notification
        self.trigger_countdown_timer = QTimer(self)
        self.trigger_countdown_timer.timeout.connect(self.tick_trigger_countdown)
        self.trigger_countdown_remaining_ms = 0
        self.trigger_countdown_step_ms = 1000
        self.trigger_countdown_char = ""

        self.setWindowTitle(self.parent.program_name)

        # Load window icon with fallback handling
        icon = self.load_icon_with_fallback()
        self.setWindowIcon(icon)

        # Set application-level metadata
        # This fixes app icon missing on linux taskbar
        self.app.setWindowIcon(icon)
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

    def load_icon_with_fallback(self) -> QIcon:
        """
        Load the application icon with intelligent fallback handling.

        Uses pre-resolved icon path from fix_image_paths() which implements:
        - External assets/images/ (development)
        - Bundled PyInstaller resources (production)

        Returns:
            QIcon: Loaded icon, or empty icon if loading fails.
        """
        icon_path = self.parent.images.get("icon", "")

        if not icon_path:
            logger.warning("No icon path configured after asset resolution")
            return QIcon()

        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                logger.debug(f"Successfully loaded icon: {icon_path}")
                return icon
            else:
                logger.warning(f"Icon file exists but failed to load: {icon_path}")
        else:
            logger.warning(f"Icon file not found: {icon_path}")

        logger.warning("Icon load failed; using empty icon")
        return QIcon()

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
        self.editor.trigger_snippet_saved.connect(self.on_snippet_saved_vault)
        self.editor.trigger_snippet_deleted.connect(lambda sid: self.snippet_service.remove_snippet(sid))

        # Vault: connect folder signals from the snippet table
        self.editor.table.vaultFolderClicked.connect(self.on_vault_folder_clicked)

        # Vault: locked trigger → main-thread dialog via Signal (thread-safe queued connection)
        self.vault_trigger_signal.connect(self.handle_vault_trigger_main)
        self.snippet_service.expander.vault_unlock_callback = self.on_vault_snippet_triggered

        # Trigger detection → status bar notification via Signal (thread-safe queued connection)
        self.trigger_detected_signal.connect(self.on_trigger_detected)
        self.snippet_service.expander.trigger_detected_callback = self.on_trigger_detected_from_expander

        # Dynamic [[placeholder]] fields → main-thread input dialog via Signal
        self.dynamic_placeholder_signal.connect(self.handle_dynamic_placeholder_main)
        self.snippet_service.expander.dynamic_placeholder_callback = self.on_dynamic_placeholder_triggered

        # Database migration backup notice → main-thread dialog via Signal
        # (fired from a background thread by the vault-unlock migration pass)
        self.migration_backup_signal.connect(self.show_migration_backup_notice)
        self._migration_notice_shown = False
        QTimer.singleShot(500, self.check_startup_migration_backup)

        # Vault: auto-lock fires from a background thread - dispatch UI update to main thread
        from utils.vault_manager import VaultManager
        def on_vault_locked():
            from PySide6.QtWidgets import QApplication
            if QApplication.instance():
                QTimer.singleShot(0, self.update_vault_ui)
        VaultManager.get_instance().set_lock_callback(on_vault_locked)

        # Vault startup sequence
        QTimer.singleShot(0, self.refresh_vault_folder_icons)
        QTimer.singleShot(0, self.update_vault_ui)
        QTimer.singleShot(0, self.apply_vault_timeout_from_config)
        QTimer.singleShot(0, self.maybe_unlock_vault_on_launch)
        
        layout.addWidget(self.linux_notice)
        layout.addWidget(self.editor)
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Check if we need to show UI at start
        # Default to true if setting missing
        # If skipped, we load later when opening UI.
        if self.parent.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", True):
            logger.debug("Showing UI at startup")
            QTimer.singleShot(0, self.show)

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
        self.menubar.viewBackupHistoryRequested.connect(self.handle_view_backup_history)
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
        Initialize the application system tray menu.

        Creates the tray icon with the OS-appropriate format and adds its context menu
        to the main window. The icon format is selected at runtime based on the OS.

        Returns:
            None
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
            menu.vault_unlock_signal.connect(lambda: self.show_vault_unlock(on_success=self.update_vault_ui))
            menu.vault_lock_signal.connect(self.tray_lock_vault)

            self.tray_menu = menu
            self.tray.setContextMenu(menu)
            self.tray.show()

            # Set initial vault action visibility
            vm = self.vault_manager()
            cfg = self.vault_config()
            menu.update_vault_state(vm.is_setup(cfg), vm.is_unlocked())

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

    def swap_database(self, new_path: Path) -> None:
        """Hot-swap the snippet database to a new path without restarting the app."""
        logger.info("Swapping database to %s", new_path)
        was_running = self.snippet_service.active()

        self.snippet_service.shutdown()
        self.parent.snippet_db.close()

        self.parent.snippet_db_file = new_path
        from utils.snippet_db import SnippetDB
        self.parent.snippet_db = SnippetDB(new_path)

        self.snippet_service = SnippetService(new_path, settings_provider=lambda: self.parent.settings)
        self.snippet_service.expander.vault_unlock_callback = self.on_vault_snippet_triggered
        self.snippet_service.expander.trigger_detected_callback = self.on_trigger_detected_from_expander
        self.snippet_service.expander.dynamic_placeholder_callback = self.on_dynamic_placeholder_triggered

        if was_running:
            self.start_service()

        self.refresh_vault_folder_icons()

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
        Update the status bar based on the current, authoritative service state.

        Reads status directly from the snippet service rather than the cached
        self.state so the status bar reliably reflects reality (e.g. paused-while-
        running is otherwise indistinguishable from running via self.state alone).

        Returns:
            None
        """
        logger.debug("Checking service status")

        if not self.snippet_service.active():
            self.update_status_bar("Stopped")
        elif self.snippet_service.is_paused():
            self.update_status_bar("Paused")
        else:
            self.update_status_bar("Running")

    def update_status_bar(self, status: str) -> None:
        """
        Update the status bar message.

        Args:
            status (str): The service status string to display.

        Returns:
            None
        """
        try:
            self.statusBar().showMessage(f"Service status: {status}")
        except Exception as e:
            logger.exception(f"Failed to update status bar: {e}")

    def show_snippets_loaded_message(self) -> None:
        """
        Display a temporary message showing loaded snippets count and DB path.
        Auto-hides after 10 seconds and restores service status.
        """
        try:
            db_path = str(self.parent.snippet_db_file)
            snippet_count = self.parent.snippet_db.get_snippet_count()

            # Truncate path to ~50 chars for display
            display_path = db_path
            if len(db_path) > 50:
                display_path = "..." + db_path[-47:]

            message = f"Loaded {snippet_count} snippets from {display_path}"

            status_bar = self.statusBar()
            status_bar.showMessage(message)

            # Set tooltip with full path on the status bar
            status_bar.setToolTip(f"Database: {db_path}")

            # Clear message after a few seconds and restore the real service status
            QTimer.singleShot(5000, self.check_service_status)

        except Exception as e:
            logger.exception(f"Failed to show snippets loaded message: {e}")

    def on_trigger_detected_from_expander(self, prefix_char: str, timeout_seconds) -> None:
        """
        Called from the expander's keyboard-listener thread when a
        trigger-prefix character starts a new potential trigger. Re-emits as
        a Qt signal so the status bar update happens on the main thread.

        Args:
            prefix_char (str): The special character that started the
                potential trigger (e.g. "/").
            timeout_seconds (float | None): The configured trigger timeout,
                or None when disabled.

        Returns:
            None
        """
        self.trigger_detected_signal.emit(prefix_char, timeout_seconds)

    def on_trigger_detected(self, prefix_char: str, timeout_seconds) -> None:
        """
        Show a status bar notification for a detected trigger prefix
        character, counting down to when the trigger buffer will expire
        from inactivity.

        Restores the real service status once the countdown reaches zero
        (or after a fixed display period when the timeout is disabled).

        Args:
            prefix_char (str): The special character that started the
                potential trigger (e.g. "/").
            timeout_seconds (float | None): The configured trigger timeout,
                or None when disabled.

        Returns:
            None
        """
        try:
            self.trigger_countdown_timer.stop()
            self.trigger_countdown_char = prefix_char

            if timeout_seconds is None:
                self.statusBar().showMessage(f"Detected Trigger: {prefix_char} (Off)")
                QTimer.singleShot(3000, self.check_service_status)
                return

            # Whole-second countdowns tick once a second; sub-second
            # ("500ms"-style) timeouts tick more finely so the countdown
            # is still visible.
            self.trigger_countdown_step_ms = 1000 if timeout_seconds >= 1 else 100
            self.trigger_countdown_remaining_ms = round(timeout_seconds * 1000)

            self.show_trigger_countdown()
            self.trigger_countdown_timer.start(self.trigger_countdown_step_ms)
        except Exception:
            logger.exception("Failed to show trigger detected message")

    def show_trigger_countdown(self) -> None:
        """
        Render the current trigger countdown state to the status bar.

        Returns:
            None
        """
        from utils.keyboard_utils import format_duration_seconds
        label = format_duration_seconds(self.trigger_countdown_remaining_ms / 1000.0)
        self.statusBar().showMessage(f"Detected Trigger: {self.trigger_countdown_char} ({label})")

    def tick_trigger_countdown(self) -> None:
        """
        Advance the trigger countdown by one step, updating the status bar.

        Stops the countdown and restores the real service status once the
        remaining time reaches zero.

        Returns:
            None
        """
        self.trigger_countdown_remaining_ms -= self.trigger_countdown_step_ms
        if self.trigger_countdown_remaining_ms <= 0:
            self.trigger_countdown_timer.stop()
            self.check_service_status()
            return
        self.show_trigger_countdown()

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
        Import snippets via wizard dialog and refresh service and UI.

        Returns:
            None
        """
        from PySide6.QtWidgets import QFileDialog
        from ui.widgets.import_export_wizard import ImportExportWizard

        logger.info("Importing snippets via menu action")

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Snippets from YAML",
            str(Path.home()),
            "YAML Files (*.yaml *.yml)"
        )
        if not path:
            logger.debug("Import cancelled by user")
            return

        vm = self.vault_manager()
        cfg = self.vault_config()
        if vm.is_setup(cfg) and not vm.is_unlocked():
            self.show_vault_unlock(
                message="Unlock the vault before importing to ensure vault folders are accessible.",
                on_success=lambda: self.run_import_wizard(Path(path)),
            )
            return

        self.run_import_wizard(Path(path))

    def run_import_wizard(self, path: Path) -> None:
        from ui.widgets.import_export_wizard import ImportExportWizard
        vm = self.vault_manager()
        cfg = self.vault_config()
        self.import_export_wizard = ImportExportWizard(
            mode="import",
            snippet_db=self.parent.snippet_db,
            import_path=path,
            parent=self,
            vault_manager=vm if vm.is_setup(cfg) else None,
        )
        self.import_export_wizard.exec()
        self.snippet_service.refresh()
        self.refresh_vault_folder_icons()

    def handle_export_action(self) -> None:
        """
        Export snippets via wizard dialog and refresh service and UI.

        Returns:
            None
        """
        logger.info("Exporting snippets via menu action")

        vm = self.vault_manager()
        cfg = self.vault_config()
        if vm.is_setup(cfg) and not vm.is_unlocked():
            self.show_vault_unlock(
                message="Unlock the vault before exporting to include vault snippets.",
                on_success=self.run_export_wizard,
            )
            return

        self.run_export_wizard()

    def run_export_wizard(self) -> None:
        from ui.widgets.import_export_wizard import ImportExportWizard
        vm = self.vault_manager()
        cfg = self.vault_config()
        self.import_export_wizard = ImportExportWizard(
            mode="export",
            snippet_db=self.parent.snippet_db,
            parent=self,
            vault_manager=vm if vm.is_setup(cfg) else None,
        )
        self.import_export_wizard.exec()
        self.snippet_service.refresh()
        self.refresh_vault_folder_icons()

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
        Display the About dialog with scrollable content.

        Builds application information and shows it in a custom dialog
        with a scroll area for better UX with long content.

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

        from PySide6.QtWidgets import QDialog, QScrollArea, QLabel
        from PySide6.QtWidgets import QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {self.parent.program_name}")
        dialog.resize(600, 500)
        dialog.setMaximumWidth(600)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title (outside scroll area)
        title_label = QLabel(f"<h2>{self.parent.program_name}</h2>")
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content_label = QLabel(info["html"])
        content_label.setTextFormat(Qt.RichText)
        content_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        content_label.setOpenExternalLinks(True)
        content_label.setWordWrap(True)
        content_label.setMargin(10)

        scroll.setWidget(content_label)
        layout.addWidget(scroll)

        dialog.exec()

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

            # Bundle mode
            bundled = hasattr(sys, "_MEIPASS")
            bundle_mode = "PyInstaller Bundle" if bundled else "Source / Development"

            # Asset paths
            icons_path = parent.images_path.parent / "icons"
            images_path = parent.images_path

            # ----- HTML VERSION -----
            html = f"""
            <b>Build Information</b><br>
            Version: {BUILD_VERSION}<br>
            Build Date: {BUILD_DATE}<br>
            Commit: {BUILD_COMMIT}<br>
            Estimated Install Date: {install_date}<br><br>

            <b>Environment</b><br>
            Runtime Mode: {bundle_mode}<br>
            Python: {platform.python_version()}<br>
            OS: {os_name} ({os_version})<br><br>

            <b>Application Directories</b><br>
            App Data: <a href="file:///{parent.app_data_dir}">{parent.app_data_dir}</a><br>
            Logs: <a href="file:///{parent.logs_dir}">{parent.logs_dir}</a><br>
            Total Log Size: {log_size_mb} MB<br><br>

            <b>Asset Directories</b><br>
            Icons: <a href="file:///{icons_path}">{icons_path}</a><br>
            Images: <a href="file:///{images_path}">{images_path}</a><br><br>

            <b>Config Files</b><br>
            Config: <a href="file:///{config_file}">{config_file}</a><br>
            Settings: <a href="file:///{settings_file}">{settings_file}</a><br><br>

            <b>Support Information</b><br>
            Email: <a href="mailto:{support_email}">{support_email}</a><br>
            Website: <a href="{support_site}">{support_site}</a><br><br>

            <b>License</b><br>
            GPLv3 © 2026 Queball1999<br>
            License: <a href="file:///{license_file}">{license_file}</a><br><br>

            <b>Icon Attribution</b><br>
            Icons provided by <a href="https://pictogrammers.com/">Pictogrammers</a> (Apache 2.0 License)<br><br>
            """

            # ----- TEXT VERSION (for logs ZIP) -----
            text = (
                f"{name}\n\n"
                f"Build Information\n"
                f"Version: {BUILD_VERSION}\n"
                f"Build Date: {BUILD_DATE}\n"
                f"Commit: {BUILD_COMMIT}\n"
                f"Estimated Install Date: {install_date}\n\n"
                f"Environment\n"
                f"Runtime Mode: {bundle_mode}\n"
                f"Python: {platform.python_version()}\n"
                f"OS: {os_name} ({os_version})\n\n"
                f"Application Directories\n"
                f"App Data: {parent.app_data_dir}\n"
                f"Logs: {parent.logs_dir}\n"
                f"Total Log Size: {log_size_mb} MB\n\n"
                f"Asset Directories\n"
                f"Icons: {icons_path}\n"
                f"Images: {images_path}\n\n"
                f"Config Files\n"
                f"Config: {config_file}\n"
                f"Settings: {settings_file}\n\n"
                f"Support Information\n"
                f"Email: {support_email}\n"
                f"Website: {support_site}\n\n"
                f"License\n"
                f"GPLv3 © 2026 Queball1999\n"
                f"License: {license_file}\n\n"
                f"Icon Attribution\n"
                f"Icons provided by Pictogrammers (https://pictogrammers.com/) - Apache 2.0 License\n"
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
        from ui.widgets.settings.vault_settings_page import VaultSettingsPage
        from ui.widgets.settings.db_settings_page import DbSettingsPage

        vault_page = VaultSettingsPage(window=self)
        db_page = DbSettingsPage(window=self)

        self.settings_dialog = SettingsDialog(
            settings=self.parent.settings,
            save_callback=self.save_settings,
            parent=self,
            extra_pages=[("Vault", vault_page), ("Database", db_page)],
        )
        self.settings_dialog.exec()

    def save_settings(self, settings: dict) -> None:
        """
        Save current settings to file.

        Updates the in-memory settings reference and writes the settings
        to the settings YAML file. Re-applies theme if appearance settings
        (theme, ui_scale, accent_color) have changed.

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

        # Recompute and re-apply style/font surfaces after any settings save.
        # Settings are edited in-place in the dialog, so old/new comparison here
        # is unreliable. Keep this path deterministic and always refresh.
        self.refresh_font_display()

        # Refresh the tray settings
        self.tray.contextMenu().refresh()

    def refresh_font_display(self) -> None:
        """
        Full refresh of every font-dependent widget after an advanced-appearance change.

        Call this whenever font family, font size, or button sizes change while the
        app is running.  safe to call multiple times.
        """
        # Recompute QFont objects and re-apply QSS/theme
        self.parent.scale_ui_cfg()

        # Propagate new family to every widget that hasn't had setFont() called
        # explicitly - this covers status bars, group boxes, tab bars, etc.
        self.parent.apply_fonts_to_all_widgets()

        # Size-specific overrides (non-medium widgets)
        self.editor.applyStyles()

        if hasattr(self, 'settings_dialog') and self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.applyStyles()

        if hasattr(self, 'placeholder_dialog') and self.placeholder_dialog and self.placeholder_dialog.isVisible():
            self.placeholder_dialog.applyStyles()

        self.app.processEvents()

    # Vault
    def vault_db(self):
        """Return the main app's snippet DB (used for vault operations)."""
        return self.parent.snippet_db

    def vault_config(self) -> dict:
        return self.parent.cfg

    def vault_manager(self):
        from utils.vault_manager import VaultManager
        return VaultManager.get_instance()

    def maybe_unlock_vault_on_launch(self) -> None:
        """Show vault unlock dialog on startup when 'unlock on launch' is configured."""
        try:
            cfg = self.vault_config()
            vm = self.vault_manager()
            if vm.is_setup(cfg) and cfg.get("vault", {}).get("unlock_on_launch", False):
                self.show_vault_unlock(on_success=self.update_vault_ui)
        except Exception:
            pass

    def apply_vault_timeout_from_config(self) -> None:
        """Apply the saved auto-lock timeout from config to VaultManager."""
        try:
            minutes = self.vault_config().get("vault", {}).get("auto_lock_minutes", 15)
            self.vault_manager().set_auto_lock_minutes(int(minutes))
        except Exception:
            pass

    def update_vault_ui(self) -> None:
        """Sync toolbar vault button, table lock state, and clipboard with VaultManager state."""
        vm = self.vault_manager()
        cfg = self.vault_config()
        is_setup = vm.is_setup(cfg)
        is_unlocked = vm.is_unlocked()
        if is_unlocked and not vm._aad_migration_done:
            vm._aad_migration_done = True  # set before dispatch to avoid duplicate threads
            db = self.vault_db()
            threading.Thread(
                target=lambda: vm.migrate_existing_vault_snippets_aad(db),
                daemon=True,
            ).start()
        if is_unlocked and not vm._brace_migration_done:
            vm._brace_migration_done = True  # set before dispatch to avoid duplicate threads
            db = self.vault_db()
            threading.Thread(
                target=lambda: self._run_vault_brace_migration(vm, db),
                daemon=True,
            ).start()
        if hasattr(self, "toolbar"):
            self.toolbar.update_vault_state(is_setup, is_unlocked)
        if hasattr(self, "menubar"):
            self.menubar.update_vault_state(is_setup, is_unlocked)
        if hasattr(self, "tray_menu"):
            self.tray_menu.update_vault_state(is_setup, is_unlocked)
        # Update table lock state; reload snippets when the state transitions
        # so load_entries can filter vault rows in or out correctly.
        if hasattr(self, "editor") and hasattr(self.editor, "table"):
            table = self.editor.table
            prev_locked = getattr(table, "vault_locked", None)
            new_locked = is_setup and not is_unlocked
            table.set_vault_lock_state(new_locked, is_setup=is_setup)
            if prev_locked != new_locked:
                self.editor.load_snippets()
        # Clear clipboard when vault locks to prevent lingering sensitive content
        if is_setup and not is_unlocked:
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().clear()
            except Exception:
                pass

    def _run_vault_brace_migration(self, vm, db) -> None:
        """Background-thread worker: run the vault-unlock placeholder-brace
        migration, then notify the main thread if it took a backup."""
        vm.migrate_existing_vault_snippets_braces(db)
        if db.pending_migration_backup_path or db.pending_migration_export_path:
            self.migration_backup_signal.emit(
                db.pending_migration_backup_path, db.pending_migration_export_path
            )

    def check_startup_migration_backup(self) -> None:
        """Show the migration-backup notice if SnippetDB backed up data at startup."""
        db = getattr(self.parent, "snippet_db", None)
        if db is None:
            return
        backup_path = getattr(db, "pending_migration_backup_path", None)
        export_path = getattr(db, "pending_migration_export_path", None)
        if backup_path or export_path:
            self.show_migration_backup_notice(backup_path, export_path)

    def show_migration_backup_notice(self, backup_path, export_path) -> None:
        """Inform the user that a database update backed up their snippets first."""
        if self._migration_notice_shown:
            return
        self._migration_notice_shown = True
        try:
            self.record_migration_backup(backup_path, export_path)
            self.show_backup_links_dialog(
                "Database Updated",
                "QSnippet updated its snippet database for this version.\n"
                "Before making any changes, a backup was saved:",
                [{"timestamp": datetime.now().isoformat(timespec="seconds"),
                  "db_backup_path": str(backup_path) if backup_path else None,
                  "export_path": str(export_path) if export_path else None}],
            )
        except Exception:
            logger.exception("Failed to show migration backup notice")

    def record_migration_backup(self, backup_path, export_path) -> None:
        """Persist a migration-backup entry so it can be recalled later from
        Help > Backup History, even if the one-time notice was dismissed."""
        try:
            backups = self.parent.settings.setdefault("backups", {})
            entry = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "db_backup_path": str(backup_path) if backup_path else None,
                "export_path": str(export_path) if export_path else None,
            }
            history = list(backups.get("database_backups", {}).get("value", []))
            history.append(entry)
            history = history[-20:]  # keep it bounded; migrations are rare

            if "database_backups" in backups:
                backups["database_backups"]["value"] = history
            else:
                backups["database_backups"] = {
                    "type": "list",
                    "value": history,
                    "hidden": True,
                    "description": "History of automatic pre-migration database backups.",
                }

            FileUtils.write_yaml(self.parent.settings_file, self.parent.settings)
        except Exception:
            logger.exception("Failed to record migration backup history")

    def handle_view_backup_history(self) -> None:
        """Help menu action: show every automatic pre-migration backup on record."""
        history = (
            self.parent.settings.get("backups", {})
            .get("database_backups", {})
            .get("value", [])
        )
        if not history:
            self.parent.message_box.info(
                "No automatic database backups have been made yet.",
                title="Backup History",
            )
            return
        self.show_backup_links_dialog(
            "Backup History",
            "Automatic backups QSnippet has made before database updates:",
            list(reversed(history)),
        )

    def show_backup_links_dialog(self, title: str, intro: str, entries: list) -> None:
        """Show *entries* (each with timestamp/db_backup_path/export_path) as a
        rich-text message box with clickable links that reveal each file in
        the OS file manager."""
        rows = []
        for entry in entries:
            parts = [f"<b>{entry.get('timestamp', '')}</b>"]
            db_path = entry.get("db_backup_path")
            export_path = entry.get("export_path")
            if db_path:
                safe = html.escape(db_path)
                parts.append(f"Database copy: <a href=\"{safe}\">{safe}</a>")
            if export_path:
                safe = html.escape(export_path)
                parts.append(f"Snippet export: <a href=\"{safe}\">{safe}</a>")
            rows.append("<br>".join(parts))
        body = html.escape(intro).replace("\n", "<br>") + "<br><br>" + "<br><br>".join(rows)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.RichText)
        box.setText(body)
        box.setStandardButtons(QMessageBox.Ok)

        label = box.findChild(QLabel, "qt_msgbox_label") or box.findChild(QLabel)
        if label:
            label.setTextInteractionFlags(Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse)
            label.setOpenExternalLinks(False)
            label.linkActivated.connect(self.reveal_in_file_manager)

        box.exec()

    def reveal_in_file_manager(self, path_str: str) -> None:
        """Open the OS file manager, selecting *path_str* if the platform supports it."""
        try:
            path = Path(path_str)
            if sys.platform == "win32":
                import subprocess
                subprocess.run(["explorer", f"/select,{path}"])
            elif sys.platform == "darwin":
                import subprocess
                subprocess.call(["open", "-R", str(path)])
            else:
                import subprocess
                subprocess.call(["xdg-open", str(path.parent)])
        except Exception:
            logger.exception("Failed to reveal %s in file manager", path_str)

    def toggle_vault_lock(self) -> None:
        """Lock if unlocked; unlock if locked; set up if not configured."""
        vm = self.vault_manager()
        cfg = self.vault_config()
        if not vm.is_setup(cfg):
            self.show_vault_settings()
        elif vm.is_unlocked():
            vm.lock()
            self.update_vault_ui()
        else:
            self.show_vault_unlock(on_success=self.update_vault_ui)

    def tray_lock_vault(self) -> None:
        """Lock vault from the tray menu and refresh tray state."""
        self.vault_manager().lock()
        self.update_vault_ui()

    def refresh_vault_folder_icons(self) -> None:
        try:
            vf = list(self.vault_db().get_vault_folders())
            # Always show the default Vault folder node even before vault is configured
            if "Vault" not in vf:
                vf.append("Vault")
            self.editor.table.set_vault_folders(vf)
            # Keep expander's vault folder set in sync for trigger intercept
            self.snippet_service.expander.set_vault_folders(vf)
            # Apply lock state before loading so load_entries filters vault rows correctly
            vm = self.vault_manager()
            cfg = self.vault_config()
            is_setup = vm.is_setup(cfg)
            self.editor.table.set_vault_lock_state(
                is_setup and not vm.is_unlocked(),
                is_setup=is_setup,
            )
            # Reload table so vault folder nodes and icons are applied immediately
            self.editor.load_snippets()
        except Exception:
            pass

    def on_snippet_saved_vault(self, entry: dict) -> None:
        """Intercept snippet form saves to encrypt when destination is a vault folder.

        The snippet form always writes plaintext content to the DB via
        ``insert_snippet``.  This handler then either encrypts the content
        (destination is vault) or clears the ``is_encrypted`` flag (moved out
        of vault, content already plaintext).

        Drag-and-drop moves are handled by ``on_snippet_moved`` via
        ``insert_snippet_vault_aware`` and do **not** pass through here.
        """
        try:
            db = self.vault_db()
            folder = entry.get("folder", "")
            snippet_id = entry.get("id")
            vm = self.vault_manager()

            logger.debug("on_snippet_saved_vault: id=%s folder=%s", snippet_id, folder)

            if db.is_under_vault_folder(folder):
                logger.info("Snippet %s saved to vault folder '%s'; proceeding with encryption", snippet_id, folder)
                if not vm.is_unlocked():
                    logger.debug("Vault locked; showing unlock dialog")
                    self.show_vault_unlock(
                        message="Unlock vault to save to this folder.",
                        on_success=lambda: self.encrypt_and_save(snippet_id, vm)
                    )
                    return
                ok = self.encrypt_and_save(snippet_id, vm)
                if not ok:
                    logger.error("Encryption failed for snippet %s", snippet_id)
                    self.parent.message_box.warning(
                        "Snippet was saved but encryption failed. "
                        "Please unlock the vault and try saving again.",
                        title="Encryption Failed",
                    )
            else:
                logger.debug("Snippet %s not in vault folder; checking if previously encrypted", snippet_id)
                # The form wrote plaintext to the DB. If the snippet was previously
                # encrypted (moved out of a vault folder), clear the flag only.
                # No decrypt is needed - the form already provides plaintext.
                db_snippet = db.get_snippet(snippet_id) or {}
                if db_snippet.get("is_encrypted"):
                    try:
                        db.set_snippet_encrypted(snippet_id, False)
                    except Exception as exc:
                        logger.error(
                            "Failed to clear is_encrypted for snippet %s: %s",
                            snippet_id, exc,
                        )
                        self.parent.message_box.warning(
                            "The snippet was saved but its vault encryption flag could "
                            "not be cleared. If this persists, try re-saving the snippet.",
                            title="Vault Warning",
                        )

            self.snippet_service.refresh_snippet(entry)
        except Exception as exc:
            logger.exception("Unexpected error in on_snippet_saved_vault: %s", exc)
            self.snippet_service.refresh_snippet(entry)

    def encrypt_and_save(self, snippet_id: int, vm) -> bool:
        """Encrypt and save a snippet in the vault. Returns True if successful."""
        try:
            import uuid as _uuid
            db = self.vault_db()
            snippet = db.get_snippet(snippet_id)
            if not snippet:
                logger.error("Snippet %s not found in database for encryption", snippet_id)
                return False
            # Always re-encrypt: the form decrypts before display, so snippet
            # content in the DB is always plaintext at this point regardless
            # of the is_encrypted flag.
            vault_uuid = str(_uuid.uuid4())
            logger.debug("Encrypting snippet %s with vault_uuid %s", snippet_id, vault_uuid)
            cipher = vm.encrypt(snippet.get("snippet", ""), aad=vault_uuid.encode())
            db.update_snippet_vault_uuid(snippet_id, cipher, vault_uuid)
            db.set_snippet_encrypted(snippet_id, True)
            vm.reset_activity_timer()

            # Verify it was marked encrypted
            verify = db.get_snippet(snippet_id)
            if verify and verify.get("is_encrypted"):
                logger.info("Snippet %s successfully encrypted and marked in database", snippet_id)
                return True
            else:
                logger.error("Snippet %s encryption flag not set after encryption!", snippet_id)
                return False
        except Exception as exc:
            logger.error("Failed to encrypt snippet %s: %s", snippet_id, exc)
            return False

    def mark_folder_vault(self, folder_path: str) -> None:
        try:
            db = self.vault_db()
            vm = self.vault_manager()

            existing = db.get_snippets_by_folder(folder_path)
            is_new_empty_folder = len(existing) == 0

            db.add_vault_folder(folder_path)

            # Encrypt all existing snippets in the folder
            import uuid as _uuid
            for snippet in existing:
                if not snippet.get("is_encrypted"):
                    try:
                        vault_uuid = str(_uuid.uuid4())
                        cipher = vm.encrypt(snippet.get("snippet", ""), aad=vault_uuid.encode())
                        db.update_snippet_vault_uuid(snippet["id"], cipher, vault_uuid)
                        db.set_snippet_encrypted(snippet["id"], True)
                    except Exception as exc:
                        logger.error("Failed to encrypt snippet %s: %s", snippet.get("id"), exc)

            # Seed a welcome snippet when creating a brand-new empty vault folder
            if is_new_empty_folder and vm.is_unlocked():
                self.insert_vault_welcome_snippet(db, vm, folder_path)

            vm.reset_activity_timer()
            self.refresh_vault_folder_icons()
            self.update_vault_ui()
            self.editor.load_snippets()
            self.snippet_service.refresh()
        except Exception as exc:
            logger.error("Failed to mark folder as vault: %s", exc)

    def insert_vault_welcome_snippet(self, db, vm, folder_path: str) -> None:
        """Insert an encrypted welcome snippet into a newly created vault folder."""
        try:
            import uuid as _uuid
            plain = (
                "Welcome to QSnippet Vault!\n\n"
                "This folder is encrypted with AES-256-GCM. "
                "Add snippets here for personal information you paste frequently - "
                "addresses, account numbers, and similar private data.\n\n"
                "Remember: the Vault is not a replacement for a dedicated password manager."
            )
            vault_uuid = str(_uuid.uuid4())
            cipher = vm.encrypt(plain, aad=vault_uuid.encode())
            entry = {
                "enabled": True,
                "label": "Welcome to the Vault",
                "trigger": "/vault",
                "snippet": cipher,
                "paste_style": "Clipboard",
                "return_press": False,
                "folder": folder_path,
                "tags": "vault,welcome",
            }
            db.insert_snippet(entry)  # sets entry["id"] as a side effect
            if entry.get("id"):
                db.set_snippet_encrypted(entry["id"], True)
                db.set_snippet_vault_uuid(entry["id"], vault_uuid)
        except Exception as exc:
            logger.warning("Could not create vault welcome snippet: %s", exc)

    def on_vault_folder_clicked(self, folder_path: str) -> None:
        """Open setup wizard if vault not configured; otherwise show unlock dialog when locked."""
        vm = self.vault_manager()
        cfg = self.vault_config()
        if not vm.is_setup(cfg):
            self.show_vault_settings()
        elif not vm.is_unlocked():
            self.show_vault_unlock(
                message=f"Unlock the vault to access: {folder_path}",
                on_success=self.update_vault_ui,
            )

    def show_vault_unlock(self, message: str = "", on_success=None) -> None:
        from ui.widgets.vault_unlock_dialog import VaultUnlockDialog
        dlg = VaultUnlockDialog(self.vault_config(), parent=self, message=message)
        dlg.unlocked.connect(lambda _: self.update_vault_ui())
        if on_success:
            dlg.unlocked.connect(lambda _: on_success())
        dlg.exec()
        if dlg.recovery_was_used:
            self.show_forced_password_reset()

    def show_forced_password_reset(self) -> None:
        from ui.widgets.vault_setup_dialog import VaultSetupDialog
        dlg = VaultSetupDialog(self.vault_config(), self.vault_db(), mode="force_reset", parent=self)
        def on_configured(updated):
            self.parent.cfg = updated
            self.apply_vault_timeout_from_config()
            self.update_vault_ui()
        dlg.vaultConfigured.connect(on_configured)
        dlg.exec()

    def on_dynamic_placeholder_triggered(self, trigger: str, snippet_entry: dict,
                                          style: str, return_press: bool) -> None:
        """Called from expander background thread when a snippet has [[name]] fields to fill in."""
        self.dynamic_placeholder_signal.emit(trigger, snippet_entry, style, return_press)

    def handle_dynamic_placeholder_main(self, trigger: str, snippet_entry: dict,
                                         style: str, return_press: bool) -> None:
        try:
            expander = self.snippet_service.expander
            plain = snippet_entry.get("snippet", "")
            self._expand_with_dynamic_placeholders(expander, trigger, plain, style, return_press)
        except Exception as exc:
            logger.error("handle_dynamic_placeholder_main failed: %s", exc)

    def _expand_with_dynamic_placeholders(self, expander, trigger: str, plain_text: str,
                                           style: str, return_press: bool) -> None:
        """
        Expand a snippet, prompting for any [[name]] fields it needs first.

        If the snippet has no dynamic placeholders, expands immediately.
        Otherwise shows an input dialog (single form or step-by-step,
        per the configured setting); cancelling aborts the paste entirely.
        """
        names = expander.get_dynamic_placeholder_names(plain_text)
        if not names:
            with expander.buffer_lock:
                expander.buffer = trigger
                expander.cursor_pos = len(trigger)
            expander.expand(trigger, plain_text, style, return_press)
            expander.clear_buffer()
            return

        from ui.widgets.dynamic_placeholder_dialog import DynamicPlaceholderDialog
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QDialog
        mode = expander.get_dynamic_placeholder_dialog_mode()
        dlg = DynamicPlaceholderDialog(names, mode=mode, parent=self)
        # Stay on top even when the main window is hidden (minimized to tray)
        dlg.setWindowFlags(dlg.windowFlags() | _Qt.WindowStaysOnTopHint)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec() != QDialog.Accepted:
            expander.clear_buffer()
            return

        with expander.buffer_lock:
            expander.buffer = trigger
            expander.cursor_pos = len(trigger)
        expander.expand(trigger, plain_text, style, return_press, dynamic_values=dlg.values)
        expander.clear_buffer()

    def on_vault_snippet_triggered(self, trigger: str, snippet_entry: dict,
                                    style: str, return_press: bool) -> None:
        """Called from expander background thread when a locked vault snippet is triggered."""
        self.vault_trigger_signal.emit(trigger, snippet_entry, style, return_press)

    def handle_vault_trigger_main(self, trigger: str, snippet_entry: dict,
                                   style: str, return_press: bool) -> None:
        try:
            vm = self.vault_manager()

            # If vault was unlocked between trigger detection and now, expand directly.
            if vm.is_unlocked():
                expander = self.snippet_service.expander
                try:
                    if snippet_entry.get("is_encrypted"):
                        aad = (snippet_entry.get("vault_uuid") or "").encode()
                        plain = vm.decrypt(snippet_entry.get("snippet", ""), aad=aad)
                    else:
                        plain = snippet_entry.get("snippet", "")
                    vm.reset_activity_timer()
                    self._expand_with_dynamic_placeholders(expander, trigger, plain, style, return_press)
                except Exception as exc:
                    logger.error("Direct vault expand failed: %s", exc)
                return

            from ui.widgets.vault_unlock_dialog import VaultUnlockDialog
            from PySide6.QtCore import Qt as _Qt
            dlg = VaultUnlockDialog(
                self.vault_config(), parent=self,
                message=f"Unlock vault to paste snippet: {snippet_entry.get('label', trigger)}"
            )
            # Stay on top even when the main window is hidden (minimized to tray)
            dlg.setWindowFlags(dlg.windowFlags() | _Qt.WindowStaysOnTopHint)

            def after_unlock(_):
                try:
                    inner_vm = self.vault_manager()
                    if snippet_entry.get("is_encrypted"):
                        raw = snippet_entry.get("snippet", "")
                        try:
                            aad = (snippet_entry.get("vault_uuid") or "").encode()
                            plain = inner_vm.decrypt(raw, aad=aad)
                        except Exception:
                            logger.warning("Decrypt failed for '%s'; using raw content", trigger)
                            plain = raw
                    else:
                        plain = snippet_entry.get("snippet", "")
                    inner_vm.reset_activity_timer()
                    self.update_vault_ui()
                    expander = self.snippet_service.expander

                    def do_expand():
                        # Buffer was cleared before dialog; restore happens
                        # inside _expand_with_dynamic_placeholders itself.
                        self._expand_with_dynamic_placeholders(expander, trigger, plain, style, return_press)

                    # Delay so the dialog fully closes and the OS returns focus
                    # to the original application before backspaces are sent
                    # (or the [[placeholder]] dialog opens, if needed).
                    QTimer.singleShot(150, do_expand)
                except Exception as exc:
                    logger.error("Failed to decrypt and expand vault snippet: %s", exc)

            dlg.unlocked.connect(after_unlock)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            dlg.exec()
            if dlg.recovery_was_used:
                self.show_forced_password_reset()
        except Exception as exc:
            logger.error("handle_vault_trigger_main failed: %s", exc)

    def show_vault_settings(self) -> None:
        """Open vault management dialog (change or disable password) from settings."""
        from ui.widgets.vault_setup_dialog import VaultSetupDialog
        cfg = self.vault_config()
        vm = self.vault_manager()
        is_first_setup = not vm.is_setup(cfg)
        mode = "change" if not is_first_setup else "setup"
        dlg = VaultSetupDialog(cfg, self.vault_db(), mode=mode, parent=self)

        def on_vault_configured(updated):
            self.parent.cfg = updated
            self.apply_vault_timeout_from_config()
            self.update_vault_ui()
            if is_first_setup:
                # "Vault" is already registered automatically (see SnippetDB
                # init), but nothing has encrypted its existing snippets or
                # seeded the welcome snippet yet until a password exists.
                QTimer.singleShot(0, lambda: self.mark_folder_vault("Vault"))

        dlg.vaultConfigured.connect(on_vault_configured)
        dlg.exec()

    def disable_vault(self) -> None:
        from ui.widgets.vault_setup_dialog import VaultSetupDialog
        cfg = self.vault_config()
        dlg = VaultSetupDialog(cfg, self.vault_db(), mode="disable", parent=self)

        def after_disable(updated):
            self.parent.cfg = updated
            self.refresh_vault_folder_icons()
            self.update_vault_ui()
            self.editor.load_snippets()
            self.snippet_service.refresh()

        dlg.vaultConfigured.connect(after_disable)
        dlg.exec()

    def refresh_theme_display(self) -> None:
        """Re-apply theme/scale/accent after a live change to those settings."""
        self.parent.apply_theme()
        # apply_theme → force_repaint calls applyStyles on all widgets, but the
        # generic sweep and dialog-specific refreshes still need to run.
        self.parent.apply_fonts_to_all_widgets()
        self.editor.applyStyles()
        if hasattr(self, 'settings_dialog') and self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.applyStyles()
        if hasattr(self, 'placeholder_dialog') and self.placeholder_dialog and self.placeholder_dialog.isVisible():
            self.placeholder_dialog.applyStyles()
        self.app.processEvents()

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
        QTimer.singleShot(0, self.show)
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
        if not self.confirm_discard_new_form():
            return
        logger.info("Exiting QSnippet")
        self.snippet_service.shutdown()
        self.parent.snippet_db.close()
        self.tray.hide()
        sys.exit()

    def confirm_discard_new_form(self) -> bool:
        """
        Check whether it is safe to close or quit while the snippet form is open.

        Covers both new and edit modes. Silently navigates home when there are no
        changes; shows Save / Discard / Keep Editing when there are.

        Returns:
            bool: True if the caller may proceed (close/quit), False to cancel.
        """
        if self.editor.stack.currentWidget() is not self.editor.form:
            return True

        if not self.editor.form.has_unsaved_changes():
            self.editor.show_home_widget()
            return True

        box = QMessageBox(self)
        box.setWindowTitle("Unsaved Snippet")
        box.setText(
            "The snippet form has unsaved changes.\n\n"
            "Would you like to save your changes or discard them?"
        )
        save_btn = box.addButton("Save", QMessageBox.AcceptRole)
        box.addButton("Discard", QMessageBox.DestructiveRole)
        keep_btn = box.addButton("Keep Editing", QMessageBox.RejectRole)
        box.setDefaultButton(keep_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked == keep_btn:
            return False
        if clicked == save_btn:
            self.editor.on_save()
            # If form is still showing, save failed - cancel the close
            if self.editor.stack.currentWidget() is self.editor.form:
                return False
            return True

        # Discard
        self.editor.show_home_widget()
        return True

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
        event.ignore()
        if not self.confirm_discard_new_form():
            return
        logger.debug("Close event intercepted; hiding window")
        self.editor.stop_inactivity_timer()
        self.hide()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "editor") and self.editor.stack.currentWidget() is self.editor.form:
            self.editor.start_inactivity_timer()

    def changeEvent(self, event) -> None:
        """
        Treat window (re)activation as user activity for the snippet form's
        inactivity timer, so clicking back into focus (e.g. alt-tab) reliably
        resets the countdown instead of relying only on text-field edits.
        """
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            if hasattr(self, "editor") and self.editor.stack.currentWidget() is self.editor.form:
                self.editor.reset_inactivity_timer()