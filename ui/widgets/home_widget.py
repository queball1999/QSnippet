from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QComboBox, QCheckBox,
    QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Signal


class HomeWidget(QWidget):
    new_snippet = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.main_layout = QVBoxLayout()
        # Make sure to add spacing

        self.welcome_label = QLabel("Welcome to QSnippets")
        # Make sure to remember the font 

        self.second_label = QLabel("Give your snippets a try below. Type /welcome now to see one in action.")
        
        self.test_entry = QTextEdit()

        self.third_label = QLabel("Your shortcuts insert snippets and will work anywhere on your computer. Whether you're typing in Word, Notepad or Chrome, we've got you covered.")
        self.third_label.setToolTip("""
                                    A snippet is a brief or extended block of text that appears when you type a shortcut.
                                    Snippets come in handy for text you enter often or for standard messages you send regularly.
                                    """)
        
        self.create_row = QHBoxLayout()

        self.create_label = QLabel("Go ahead and create a new snippet now.")

        self.create_button = QPushButton("New Snippet")
        self.create_button.pressed.connect(self.new_snippet.emit)

        self.create_row.addWidget(self.create_label)
        self.create_row.addWidget(self.create_button)

        self.main_layout.addWidget(self.welcome_label)
        self.main_layout.addWidget(self.second_label)
        self.main_layout.addWidget(self.test_entry)
        self.main_layout.addWidget(self.third_label)
        self.main_layout.addLayout(self.create_row)

        self.setLayout(self.main_layout)