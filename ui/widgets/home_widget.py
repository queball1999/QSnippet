from PySide6.QtWidgets import QWidget, QLabel, QTextEdit, QPushButton, QHBoxLayout, QGridLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

class HomeWidget(QWidget):
    new_snippet = Signal()
    updated = Signal()

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        
        self.initUI()
        self.applyStyles()

    def initUI(self):
        self.main_layout = QGridLayout()
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(15, 0, 0, 0)

        # Welcome Hearer w/ Logo
        self.welcome_label = QLabel("Welcome to QSnippets")
        self.second_label = QLabel("Give your snippets a try below. Type /welcome now to see one in action.")
        
        self.pixmap = QPixmap(self.main.images["icon_64"])
        self.program_logo = QLabel()
        self.program_logo.setPixmap(self.pixmap)

        self.test_entry = QTextEdit()

        self.third_label = QLabel("Your triggers insert snippets where you are typing and work with any app on your computer. Whether you're typing in Word, Notepad or Chrome, we've got you covered.")
        self.third_label.setToolTip("A snippet is a brief or extended block of text that appears when you type a shortcut.\nSnippets come in handy for text you enter often or for standard messages you send regularly.")
        self.third_label.setWordWrap(True)
        
        self.create_row = QHBoxLayout()
        self.create_label = QLabel("Go ahead and create a new snippet now")

        self.create_button = QPushButton("New Snippet")
        self.create_button.setFixedSize(self.main.small_button_size)
        self.create_button.pressed.connect(self.new_snippet.emit)

        self.create_row.addWidget(self.create_label)
        self.create_row.addWidget(self.create_button, alignment=Qt.AlignLeft)

        self.main_layout.addWidget(self.welcome_label, 0, 0, 1, 1, Qt.AlignLeft)
        self.main_layout.addWidget(self.second_label, 1, 0, 1, 1, Qt.AlignLeft)
        self.main_layout.addWidget(self.program_logo, 0, 1, 2, 1, Qt.AlignCenter)
        self.main_layout.addWidget(self.test_entry, 2, 0, 1, 2)
        self.main_layout.addWidget(self.third_label, 3, 0, 1, 2)
        self.main_layout.addLayout(self.create_row, 4, 0, 1, 1)

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
        self.setStyleSheet(f"""
            QPushButton {{
                padding: 5px
            }}""")
        
    def showEvent(self, event):
        super().showEvent(event)
        # force focus when the form is shown
        self.test_entry.setFocus(Qt.TabFocusReason)
