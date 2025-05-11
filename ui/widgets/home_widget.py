from PySide6.QtWidgets import QWidget, QLabel, QTextEdit, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont

class HomeWidget(QWidget):
    new_snippet = Signal()

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        # Buttons
        self.mini_button_size = QSize(self.main.dimensions_buttons["mini"]["width"], self.main.dimensions_buttons["mini"]["height"])
        self.small_button_size = QSize(self.main.dimensions_buttons["small"]["width"], self.main.dimensions_buttons["small"]["height"])
        # Font Sizes
        self.small_font_size = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["small"])
        self.small_font_size_bold = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["small"], QFont.Bold)
        self.medium_font_size = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["medium"])
        self.medium_font_size_bold = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["medium"], QFont.Bold)
        self.large_font_size = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["large"])
        self.large_font_size_bold = QFont(self.main.fonts["primary_font"], self.main.fonts_sizes["large"], QFont.Bold)
        
        self.initUI()

    def initUI(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(25)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        # Make sure to add spacing

        self.welcome_label = QLabel("Welcome to QSnippets")
        self.welcome_label.setFont(self.large_font_size)
        # Make sure to remember the font 

        self.second_label = QLabel("Give your snippets a try below. Type /welcome now to see one in action.")
        self.second_label.setFont(self.small_font_size)
        
        self.test_entry = QTextEdit()

        self.third_label = QLabel("Your shortcuts insert snippets and will work anywhere on your computer. Whether you're typing in Word, Notepad or Chrome, we've got you covered.")
        self.third_label.setToolTip("""A snippet is a brief or extended block of text that appears when you type a shortcut.
                                    Snippets come in handy for text you enter often or for standard messages you send regularly.""")
        self.third_label.setWordWrap(True)
        self.third_label.setFont(self.small_font_size)
        
        self.create_row = QHBoxLayout()

        self.create_label = QLabel("Go ahead and create a new snippet now")
        self.create_label.setFont(self.small_font_size)

        self.create_button = QPushButton("New Snippet")
        self.create_button.setFont(self.small_font_size)
        self.create_button.setFixedSize(self.mini_button_size)
        self.create_button.pressed.connect(self.new_snippet.emit)

        self.create_row.addWidget(self.create_label)
        self.create_row.addWidget(self.create_button, alignment=Qt.AlignLeft)

        self.main_layout.addWidget(self.welcome_label)
        self.main_layout.addWidget(self.second_label)
        self.main_layout.addWidget(self.test_entry)
        self.main_layout.addWidget(self.third_label)
        self.main_layout.addLayout(self.create_row)

        self.setLayout(self.main_layout)

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)