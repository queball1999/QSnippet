import yaml
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QMessageBox,
    QLabel, QComboBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from .QAnimatedSwitch import QAnimatedSwitch

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
        # Table: Enabled switch, Trigger, Snippet, Paste Style
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Enabled', 'Trigger', 'Snippet', 'Paste Style'])
        self.load_config()

        # Status label
        self.status_label = QLabel("Service status: Stopped")
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

    def load_config(self):
        if self.config_path.exists():
            data = yaml.safe_load(self.config_path.read_text()) or {}
            snippets = data.get('snippets', [])
        else:
            snippets = []

        self.table.setRowCount(0)
        for entry in snippets:
            row = self.table.rowCount()
            self.table.insertRow(row)
            # Enabled switch
            enabled_switch = QAnimatedSwitch(on_text='On', off_text='Off')
            enabled_switch.stateChanged.connect(lambda state, r=row: None)
            if entry.get('enabled', False):
                enabled_switch.toggle(True)
            self.table.setCellWidget(row, 0, enabled_switch)
            # Trigger
            self.table.setItem(row, 1, QTableWidgetItem(entry.get('trigger', '')))
            # Snippet
            self.table.setItem(row, 2, QTableWidgetItem(entry.get('snippet', '')))
            # Paste Style dropdown
            combo = QComboBox()
            combo.addItems(['Keystroke', 'Clipboard'])
            style = entry.get('paste_style', 'Clipboard')
            combo.setCurrentText(style)
            self.table.setCellWidget(row, 3, combo)

    def add_snippet(self):
        self._open_editor('', '', enabled=False, paste_style='Clipboard')

    def edit_snippet(self):
        row = self.table.currentRow()
        if row < 0:
            return
        trigger = self.table.item(row, 1).text()
        snippet = self.table.item(row, 2).text()
        enabled = self.table.cellWidget(row, 0).isChecked()
        style = self.table.cellWidget(row, 3).currentText()
        self._open_editor(trigger, snippet, row, enabled, style)

    def delete_snippet(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.removeRow(row)

    def _open_editor(self, trigger, snippet, row=None, enabled=False, paste_style='Clipboard'):
        dlg = QWidget()
        dlg.setWindowTitle('Edit Snippet')
        t_input = QLineEdit(trigger)
        s_input = QTextEdit(snippet)
        style_combo = QComboBox()
        style_combo.addItems(['Keystroke', 'Clipboard'])
        style_combo.setCurrentText(paste_style)
        ok = QPushButton('OK')
        cancel = QPushButton('Cancel')
        ok.clicked.connect(lambda: self._save_dialog(dlg, t_input, s_input, row, style_combo, enabled))
        cancel.clicked.connect(dlg.close)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel('Trigger:'))
        layout.addWidget(t_input)
        layout.addWidget(QLabel('Snippet:'))
        layout.addWidget(s_input)
        layout.addWidget(QLabel('Paste Style:'))
        layout.addWidget(style_combo)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)
        dlg.resize(400, 400)
        dlg.show()

    def _save_dialog(self, dlg, t_input, s_input, row, style_combo, enabled):
        trigger = t_input.text().strip()
        snippet = s_input.toPlainText()
        paste_style = style_combo.currentText()
        if not trigger:
            QMessageBox.warning(self, 'Error', 'Trigger cannot be empty')
            return
        if row is None:
            r = self.table.rowCount()
            self.table.insertRow(r)
            switch = QAnimatedSwitch(on_text='On', off_text='Off')
            if enabled:
                switch.toggle(True)
            self.table.setCellWidget(r, 0, switch)
            self.table.setItem(r, 1, QTableWidgetItem(trigger))
            self.table.setItem(r, 2, QTableWidgetItem(snippet))
            combo = QComboBox()
            combo.addItems(['Keystroke', 'Clipboard'])
            combo.setCurrentText(paste_style)
            self.table.setCellWidget(r, 3, combo)
        else:
            self.table.cellWidget(row, 0).toggle(enabled)
            self.table.setItem(row, 1, QTableWidgetItem(trigger))
            self.table.setItem(row, 2, QTableWidgetItem(snippet))
            self.table.cellWidget(row, 3).setCurrentText(paste_style)
        dlg.close()

    def save_config(self):
        snippets = []
        for row in range(self.table.rowCount()):
            enabled = self.table.cellWidget(row, 0).isChecked()
            trigger = self.table.item(row, 1).text()
            snippet = self.table.item(row, 2).text()
            paste_style = self.table.cellWidget(row, 3).currentText()
            snippets.append({
                'enabled': enabled,
                'trigger': trigger,
                'snippet': snippet,
                'paste_style': paste_style
            })
        data = {'snippets': snippets}
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f)
        QMessageBox.information(self, 'Saved', 'Configuration saved successfully')