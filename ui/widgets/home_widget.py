from PySide6.QtWidgets import QWidget, QLabel, QTextEdit, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont

class HomeWidget(QWidget):
    new_snippet = Signal()
    updated = Signal()

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        
        self.initUI()

    def initUI(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(15, 0, 0, 0)

        self.welcome_label = QLabel("Welcome to QSnippets")
        self.welcome_label.setFont(self.main.extra_large_font_size)

        self.second_label = QLabel("Give your snippets a try below. Type /welcome now to see one in action.")
        self.second_label.setFont(self.main.small_font_size)
        
        self.test_entry = QTextEdit()

        self.third_label = QLabel("Your shortcuts insert snippets and will work anywhere on your computer. Whether you're typing in Word, Notepad or Chrome, we've got you covered.")
        self.third_label.setToolTip("A snippet is a brief or extended block of text that appears when you type a shortcut.\nSnippets come in handy for text you enter often or for standard messages you send regularly.")
        self.third_label.setWordWrap(True)
        self.third_label.setFont(self.main.small_font_size)
        
        self.create_row = QHBoxLayout()

        self.create_label = QLabel("Go ahead and create a new snippet now")
        self.create_label.setFont(self.main.small_font_size)

        self.create_button = QPushButton("New Snippet")
        self.create_button.setFont(self.main.small_font_size)
        self.create_button.setFixedSize(self.main.small_button_size)
        self.create_button.pressed.connect(self.new_snippet.emit)

        self.create_row.addWidget(self.create_label)
        self.create_row.addWidget(self.create_button, alignment=Qt.AlignLeft)

        self.main_layout.addWidget(self.welcome_label)
        self.main_layout.addWidget(self.second_label)
        self.main_layout.addWidget(self.test_entry)
        self.main_layout.addWidget(self.third_label)
        self.main_layout.addLayout(self.create_row)

        self.setLayout(self.main_layout)

    def applyStyles(self):
        # Font Sizing
        self.welcome_label.setFont(self.main.extra_large_font_size)
        self.second_label.setFont(self.main.small_font_size)
        self.third_label.setFont(self.main.small_font_size)
        self.create_label.setFont(self.main.small_font_size)

        self.create_button.setFont(self.main.small_font_size)
        # Button Sizing
        self.create_button.setFixedSize(self.main.small_button_size)
        # StyleSheet
        self.update_stylesheet()

        self.layout().invalidate()
        self.update()

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)