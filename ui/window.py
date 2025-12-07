import sys
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMainWindow, QHBoxLayout, QWidget
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer

from utils.file_utils import FileUtils
from utils.reg_utils import RegUtils
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
                print(self.parent.images)
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
