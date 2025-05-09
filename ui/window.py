import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QMessageBox, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QIcon, QAction

from utils.file_utils import FileUtils
from .widgets import ConfigEditor

class TrayApp:
    def __init__(self, parent):
        self.parent = parent
        self.cfg = parent.cfg
        self.app = parent.app
        paths = FileUtils.get_default_paths()
        self.config_file = paths['working_dir'] / "snippets.yaml"

        # Show editor at startup
        self.editor = ConfigEditor(config_path=self.config_file, parent=self.parent)
        self.editor.show()

        # Path to the service script or executable
        # Will need to swap out with actial service eventually
        self.service_cmd = ['python', os.path.join(os.getcwd(), 'service.py'), '--config', str(self.config_file)]
        self.process = None

        icon = QIcon(self.parent.program_icon)
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip('QSnippet')

        menu = QMenu()
        self.start_action = QAction('Start Service')
        self.stop_action = QAction('Stop Service')
        self.edit_action = QAction('Edit Snippets')
        self.quit_action = QAction('Quit')

        self.start_action.triggered.connect(self.start_service)
        self.stop_action.triggered.connect(self.stop_service)
        self.edit_action.triggered.connect(self.editor.show)
        self.quit_action.triggered.connect(self.exit)

        menu.addAction(self.start_action)
        menu.addAction(self.stop_action)
        menu.addSeparator()
        menu.addAction(self.edit_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)

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

    def run(self):
        sys.exit(self.app.exec())