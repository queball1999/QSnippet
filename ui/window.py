import os
import sys
import subprocess
import yaml
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QTableWidget, QTableWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QMessageBox, QSystemTrayIcon,
    QMenu, QLabel
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt

from utils.file_utils import FileUtils

class ConfigEditor(QWidget):
    def __init__(self, config_path, parent):
        super().__init__()
        self.parent = parent
        self.config_path = Path(config_path)
        self.setWindowTitle('QSnippet')
        self.setWindowIcon(QIcon(self.parent.program_icon))
        self.resize(600, 400)
        self.initUI()

    def initUI(self):
        # Table for snippets
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Trigger', 'Snippet'])
        self.load_config()

        # Status label
        self.status_label = QLabel(f"Service status: Stopped")
        self.status_label.setAlignment(Qt.AlignLeft)

        # Buttons
        add_btn = QPushButton('Add')
        edit_btn = QPushButton('Edit')
        del_btn = QPushButton('Delete')
        save_btn = QPushButton('Save')

        add_btn.clicked.connect(self.add_snippet)
        edit_btn.clicked.connect(self.edit_snippet)
        del_btn.clicked.connect(self.delete_snippet)
        save_btn.clicked.connect(self.save_config)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)

    def closeEvent(self, event):
        # Override close to hide instead of exiting app
        event.ignore()
        self.hide()

    def load_config(self):
        if self.config_path.exists():
            data = yaml.safe_load(self.config_path.read_text()) or {}
            snippets = data.get('snippets', {})
        else:
            snippets = {}
        self.table.setRowCount(0)
        for trigger, snippet in snippets.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(trigger))
            self.table.setItem(row, 1, QTableWidgetItem(snippet))

    def add_snippet(self):
        self._open_editor('', '')

    def edit_snippet(self):
        row = self.table.currentRow()
        if row < 0:
            return
        trigger = self.table.item(row, 0).text()
        snippet = self.table.item(row, 1).text()
        self._open_editor(trigger, snippet, row)

    def delete_snippet(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.removeRow(row)

    def _open_editor(self, trigger, snippet, row=None):
        dlg = QWidget()
        dlg.setWindowTitle('Edit Snippet')
        t_input = QLineEdit(trigger)
        s_input = QTextEdit(snippet)
        ok = QPushButton('OK')
        cancel = QPushButton('Cancel')
        ok.clicked.connect(lambda: self._save_dialog(dlg, t_input, s_input, row))
        cancel.clicked.connect(dlg.close)
        layout = QVBoxLayout(dlg)
        layout.addWidget(t_input)
        layout.addWidget(s_input)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)
        dlg.setLayout(layout)
        dlg.resize(400, 300)
        dlg.show()

    def _save_dialog(self, dlg, t_input, s_input, row):
        trigger = t_input.text().strip()
        snippet = s_input.toPlainText()
        if not trigger:
            QMessageBox.warning(self, 'Error', 'Trigger cannot be empty')
            return
        if row is None:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(trigger))
            self.table.setItem(r, 1, QTableWidgetItem(snippet))
        else:
            self.table.setItem(row, 0, QTableWidgetItem(trigger))
            self.table.setItem(row, 1, QTableWidgetItem(snippet))
        dlg.close()

    def save_config(self):
        snippets = {}
        for row in range(self.table.rowCount()):
            trigger = self.table.item(row, 0).text()
            snippet = self.table.item(row, 1).text()
            snippets[trigger] = snippet
        data = {'snippets': snippets}
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f)
        QMessageBox.information(self, 'Saved', 'Configuration saved successfully')

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