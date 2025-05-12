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
        self.folder_input = QLineEdit(clearButtonEnabled=True)
        self.folder_input.setFont(self.main.small_font_size)

        self.label_input = QLineEdit(clearButtonEnabled=True)
        self.label_input.setFont(self.main.small_font_size)

        self.trigger_input = QLineEdit(clearButtonEnabled=True)
        self.trigger_input.setFont(self.main.small_font_size)

        self.snippet_input = QTextEdit()
        self.snippet_input.setFont(self.main.small_font_size)

        self.style_combo = QComboBox()
        self.style_combo.setFont(self.main.small_font_size)
        self.style_combo.addItems(['Keystroke', 'Clipboard'])

        # Enabled Switch Row
        self.switch_row = QHBoxLayout()
        self.enabled_switch = QAnimatedSwitch(objectName="enabled_switch",
                                           on_text="Enabled",
                                           off_text="Disabled",
                                           text_position="right",
                                           text_font=self.main.medium_font_size,
                                           toggle_size=self.main.small_toggle_size,
                                           parent=self)
        self.spacer = QLabel()
        
        self.switch_row.addWidget(self.enabled_switch)
        self.switch_row.addWidget(self.spacer)
        

        # Add labeled widgets
        for widget, title in [
            (self.enabled_switch, None),
            (self.folder_input, 'Folder:'),
            (self.label_input, 'Label:'),
            (self.trigger_input, 'Trigger:'),
            (self.snippet_input, 'Snippet:'),
            (self.style_combo, 'Paste Style:')
        ]:
            if title:
                lbl = QLabel(title)
                lbl.setFont(self.main.medium_font_size)
                layout.addWidget(lbl)
            layout.addWidget(widget)

        # Buttons
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton('New')
        self.new_btn.setFont(self.main.small_font_size)
        self.new_btn.setFixedSize(self.main.small_button_size)

        self.save_btn = QPushButton('Save')
        self.save_btn.setFont(self.main.small_font_size)
        self.save_btn.setFixedSize(self.main.small_button_size)

        self.delete_btn = QPushButton('Delete')
        self.delete_btn.setFont(self.main.small_font_size)
        self.delete_btn.setFixedSize(self.main.small_button_size)

        self.cancel_btn = QPushButton('Cancel') # Maybe rename home?
        self.cancel_btn.setFont(self.main.small_font_size)
        self.cancel_btn.setFixedSize(self.main.small_button_size)

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
        #   - Trigger must have special character as first char.
        entry = self.get_entry()
        if not entry['trigger'] or not entry['snippet']:
            QMessageBox.warning(self, 'Error', 'Trigger and snippet are required')
            return False
        return True
    
    def applyStyles(self):
        # Font Sizing
        self.folder_input.setFont(self.main.small_font_size)
        self.label_input.setFont(self.main.small_font_size)
        self.trigger_input.setFont(self.main.small_font_size)
        self.snippet_input.setFont(self.main.small_font_size)
        self.style_combo.setFont(self.main.small_font_size)
        
        self.new_btn.setFont(self.main.small_font_size)
        self.save_btn.setFont(self.main.small_font_size)
        self.delete_btn.setFont(self.main.small_font_size)
        self.cancel_btn.setFont(self.main.small_font_size)

        # Button Sizing
        self.new_btn.setFixedSize(self.main.small_button_size)
        self.save_btn.setFixedSize(self.main.small_button_size)
        self.delete_btn.setFixedSize(self.main.small_button_size)
        self.cancel_btn.setFixedSize(self.main.small_button_size)

        # Widget Styling
        self.enabled_switch.text_font = self.main.medium_font_size
        self.enabled_switch.toggle_size = self.main.small_toggle_size
        self.enabled_switch.applyStyles()

        # StyleSheet
        self.update_stylesheet()

        self.layout().invalidate()
        self.update()
    
    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)
