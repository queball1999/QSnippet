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

class QSnippet(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.cfg = parent.cfg
        self.app = parent.app

        self.setWindowTitle(self.parent.program_name)
        self.setWindowIcon(QIcon(self.parent.images["icon_16"]))

        width = self.parent.dimensions_windows["main"]["width"]
        height = self.parent.dimensions_windows["main"]["height"]
        self.resize(width, height)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.check_service_status)
        self._status_timer.start(5000)

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
        self.menubar = MenuBar(self)
        self.setMenuBar(self.menubar)

    def init_toolbar(self):
        # install the toolbar
        self.toolbar = ToolbarMenu(self)
        self.addToolBar(self.toolbar)

    def init_tray_menu(self):
        # install the system tray icon
        icon = QIcon(self.parent.images["icon_16"])
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip('QSnippet')
        # Allow left clicks of tray icon to show UI
        self.tray.activated.connect(self.on_tray_icon_activated)

        menu = TrayMenu(main=self.parent)
        menu.start_signal.connect(self.start_service)
        menu.stop_signal.connect(self.stop_service)
        menu.edit_signal.connect(self.show)
        menu.exit_signal.connect(self.exit)
        menu.startup_signal.connect(self.handle_startup_signal)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def run(self):
        sys.exit(self.app.exec())

    def start_service(self):
        self.snippet_service.start()
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Running")

    def stop_service(self):
        self.snippet_service.stop()
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Stopped")

    def check_service_status(self):
        if not self.snippet_service._thread.is_alive():
            self.statusBar().showMessage(f"Service status: Stopped")
        else:
            self.statusBar().showMessage(f"Service status: Running")

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

    def unset_skip_reg(self):
        self.parent.skip_reg = False

    def on_tray_icon_activated(self, event):
        """ Handle left-click event and show UI """
        if event == QSystemTrayIcon.Trigger:
            # Left click
            if not self.isVisible():
                self.show()
            else:
                self.raise_()  # bring to front
                self.activateWindow()

    def exit(self):
        self.stop_service()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event):
        # Override close to hide instead of exiting app
        event.ignore()
        self.hide()
