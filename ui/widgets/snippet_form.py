from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Signal
from .QAnimatedSwitch import QAnimatedSwitch

class SnippetForm(QWidget):
    # Signals to notify parent
    newClicked = Signal()
    saveClicked = Signal()
    deleteClicked = Signal()
    entryChanged = Signal(dict)
    cancelPressed = Signal()

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Form fields
        self.folder_input = QLineEdit()
        self.label_input = QLineEdit()
        self.trigger_input = QLineEdit()
        self.snippet_input = QTextEdit()
        #self.enabled_switch = QCheckBox('Enabled')
        self.style_combo = QComboBox()
        self.enabled_switch = QAnimatedSwitch(objectName="enabled_switch",
                                           on_text="Disable",
                                           off_text="Enable",
                                           text_position="left",
                                           parent=self)
        self.style_combo.addItems(['Keystroke', 'Clipboard'])

        # Add labeled widgets
        for widget, title in [
            (self.folder_input, 'Folder:'),
            (self.label_input, 'Label:'),
            (self.trigger_input, 'Trigger:'),
            (self.snippet_input, 'Snippet:'),
            (self.enabled_switch, None),
            (self.style_combo, 'Paste Style:')
        ]:
            if title:
                lbl = QLabel(title)
                layout.addWidget(lbl)
            layout.addWidget(widget)

        # Buttons
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton('New')
        self.save_btn = QPushButton('Save')
        self.delete_btn = QPushButton('Delete')
        self.cancel_btn = QPushButton('Cancel')
        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Connect signals
        self.new_btn.pressed.connect(self.newClicked)
        self.save_btn.pressed.connect(self.saveClicked)
        self.delete_btn.pressed.connect(self.deleteClicked)
        self.cancel_btn.pressed.connect(self.cancelPressed.emit)

    def clear_form(self):
        """ Clear all entries in the form. """
        self.folder_input.clear()
        self.label_input.clear()
        self.trigger_input.clear()
        self.snippet_input.clear()
        self.enabled_switch.setChecked(False)
        self.style_combo.setCurrentIndex(0)

    def load_entry(self, entry: dict):
        """
        Populate form fields from snippet entry dict
        {folder, label, trigger, snippet, enabled, paste_style}
        """
        self.folder_input.setText(entry.get('folder', ''))
        self.label_input.setText(entry.get('label', ''))
        self.trigger_input.setText(entry.get('trigger', ''))
        self.snippet_input.setPlainText(entry.get('snippet', ''))
        self.enabled_switch.setChecked(entry.get('enabled', False))
        self.style_combo.setCurrentText(entry.get('paste_style', 'Clipboard'))

    def get_entry(self) -> dict:
        """
        Read form fields into snippet entry dict
        """
        folder = self.folder_input.text().strip() or 'Default'
        label = self.label_input.text().strip()
        trigger = self.trigger_input.text().strip()
        snippet = self.snippet_input.toPlainText()
        enabled = self.enabled_switch.isChecked()
        paste_style = self.style_combo.currentText()
        return {
            'folder': folder,
            'label': label,
            'trigger': trigger,
            'snippet': snippet,
            'enabled': enabled,
            'paste_style': paste_style
        }

    def validate(self) -> bool:
        """Ensure required fields are populated"""
        # Items to Validate:
        #   - Max Trigger Length of 255
        #   - Trigger must have no spaces or newlines.
        #   - 
        entry = self.get_entry()
        if not entry['trigger'] or not entry['snippet']:
            QMessageBox.warning(self, 'Error', 'Trigger and snippet are required')
            return False
        return True
    
    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)
