import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QMessageBox, QSystemTrayIcon, QMainWindow, QHBoxLayout, QWidget
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer

from utils.file_utils import FileUtils
from .widgets import SnippetEditor
from .menus import *
from .service import *

class QSnippet(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.cfg = parent.cfg
        self.app = parent.app

        self.setWindowTitle('QSnippet')
        self.setWindowIcon(QIcon(self.parent.program_icon))

        paths = FileUtils.get_default_paths()
        self.config_file = paths['working_dir'] / "snippets.yaml"

        # Path to the service script or executable
        # Will need to swap out with actial service eventually
        #self.service_cmd = ['python', os.path.join(os.getcwd(), 'service.py'), '--config', str(self.config_file)]
        self.process = None

        width = self.parent.dimensions_windows["main"]["width"]
        height = self.parent.dimensions_windows["main"]["height"]
        self.resize(width, height)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.check_service_status)
        self._status_timer.start(5000)

        self.snippet_service = SnippetService(self.config_file)

        self.initUI()
        self.init_menubar()
        self.init_toolbar()
        self.init_tray_menu()
        self.start_service()

    def initUI(self):
        container = QWidget()
        layout = QHBoxLayout(container)

        # Show editor at startup
        self.editor = SnippetEditor(config_path=self.config_file, main=self.parent, parent=self)
        
        layout.addWidget(self.editor)
        container.setLayout(layout)
        self.setCentralWidget(container)
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
        icon = QIcon(self.parent.program_icon)
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip('QSnippet')

        menu = TrayMenu()
        menu.start_signal.connect(self.start_service)
        menu.stop_signal.connect(self.stop_service)
        menu.edit_signal.connect(self.show)
        menu.exit_signal.connect(self.exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.show)
        self.tray.show()

    def run(self):
        sys.exit(self.app.exec())

    def start_service(self):
        self.snippet_service.start()
        # should log this
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Running")

    def stop_service(self):
        self.snippet_service.stop()
        if self.editor.isVisible():
            self.statusBar().showMessage(f"Service status: Stopped")

    def check_service_status(self):
        #print('Checking Status')
        if not self.snippet_service._thread.is_alive():
            self.statusBar().showMessage(f"Service status: Stopped")
        else:
            self.statusBar().showMessage(f"Service status: Running")

    def exit(self):
        self.stop_service()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event):
        # Override close to hide instead of exiting app
        event.ignore()
        self.hide()