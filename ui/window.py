import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QMessageBox, QSystemTrayIcon, QMainWindow, QHBoxLayout, QWidget
)
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, Qt

from utils.file_utils import FileUtils
from .widgets import SnippetEditor
from .menus import *

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
        self.service_cmd = ['python', os.path.join(os.getcwd(), 'service.py'), '--config', str(self.config_file)]
        self.process = None

        width = self.parent.dimensions_windows["main"]["width"]
        height = self.parent.dimensions_windows["main"]["height"]
        self.resize(width, height)

        self.initUI()
        self.init_menubar()
        self.init_toolbar()
        self.init_tray_menu()

    def initUI(self):
        container = QWidget()
        layout = QHBoxLayout(container)

        # Show editor at startup
        self.editor = SnippetEditor(config_path=self.config_file, parent=self.parent)
        
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
        menu.quit_signal.connect(self.exit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def start_service(self):
        if self.process is None or self.process.poll() is not None:
            self.process = subprocess.Popen(self.service_cmd)
            self.editor.status_label.setText(f"Service status: Running")
            QMessageBox.information(None, 'Service', 'Snippet service started')

    def stop_service(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
            self.editor.status_label.setText(f"Service status: Stopped")
            QMessageBox.information(None, 'Service', 'Snippet service stopped')

    def exit(self):
        self.stop_service()
        self.tray.hide()
        sys.exit()

    def closeEvent(self, event):
        # Override close to hide instead of exiting app
        event.ignore()
        self.hide()

    def run(self):
        sys.exit(self.app.exec())