import logging
from PySide6.QtWidgets import (
    QWidget, QLabel, QTextEdit, QPushButton,
    QHBoxLayout, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)



class HomeWidget(QWidget):
    new_snippet = Signal()
    updated = Signal()

    def __init__(self, main, parent=None) -> None:
        """
        Initialize the HomeWidget.

        Sets up references, initializes Easter egg tracking variables,
        builds the UI, and applies styles.

        Args:
            main (Any): Reference to the main application object.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.main = main
        self.parent = parent

        # Easter Egg
        # If user clicks the logo 5 times in 5 seconds, show snail image
        self._icon_clicks = []
        self._EASTER_WINDOW = 5000  # ms
        self._EASTER_COUNT = 5
        
        self.initUI()
        self.applyStyles()

    def initUI(self) -> None:
        """
        Initialize the user interface components.

        Creates layout structure, labels, logo, test entry field,
        and new snippet button, and connects relevant signals.

        Returns:
            None
        """
        self.main_layout = QGridLayout()
        self.main_layout.setSpacing(15)
        self.main_layout.setContentsMargins(15, 0, 0, 0)

        # Welcome Hearer w/ Logo
        self.welcome_label = QLabel("Welcome to QSnippets")
        second_label_text = (
            "Give your snippets a try below. "
            "It looks like you may want to create one to test here!"
        )
        self.second_label = QLabel(second_label_text)

        self.pixmap = QPixmap(self.main.images["icon_64"])
        self.program_logo = QLabel()
        self.program_logo.setPixmap(self.pixmap)

        if self.main.settings["general"]["extra_features"]["easter_eggs_enabled"].get("value", True):
            logger.debug("Easter Eggs are enabled in HomeWidget.")
            self.program_logo.mousePressEvent = self.on_icon_clicked

        self.test_entry = QTextEdit()

        third_label_text = (
            "Your triggers insert snippets where you are typing and work with any app on your computer. "
            "Whether you're typing in Word, Notepad or Chrome, we've got you covered."
        )
        third_label_tooltip = (
            "A snippet is a brief or extended block of text that appears when you type a shortcut. "
            "Snippets come in handy for text you enter often or for standard messages you send regularly."
        )
        self.third_label = QLabel(third_label_text)
        self.third_label.setToolTip(third_label_tooltip)
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

    def on_icon_clicked(self, event: None) -> None:
        """
        Handle clicks on the program logo for Easter egg detection.

        Tracks click timestamps and triggers the Easter egg action
        if the required number of clicks occur within the time window.

        Args:
            event (None): The mouse event.

        Returns:
            None
        """
        now = QDateTime.currentMSecsSinceEpoch()
        self._icon_clicks.append(now)

        # Keep only clicks in the last 5 seconds
        cutoff = now - self._EASTER_WINDOW
        self._icon_clicks = [t for t in self._icon_clicks if t >= cutoff]

        if len(self._icon_clicks) >= self._EASTER_COUNT:
            self._icon_clicks.clear()
            self.show_snail()

    def show_snail(self) -> None:
        """
        Display the Easter egg dialog with a snail image.

        Returns:
            None
        """
        box = QMessageBox(self)
        box.setWindowTitle("Easy there partner!")
        box.setText(
            "You almost ran me over!\n" \
            "Enjoy this photo I took of a snail :)\n\n" \
            "You can turn off easter eggs in the settings.\n\n"
        )

        pixmap = QPixmap(self.main.images["snail"])
        box.setIconPixmap(pixmap.scaledToWidth(256, Qt.SmoothTransformation))

        box.exec()

    # ----- Styling Functions -----
    def applyStyles(self) -> None:
        """
        Apply fonts, sizes, and styles to UI elements.

        Returns:
            None
        """
        self.welcome_label.setFont(self.main.extra_large_font_size)
        self.second_label.setFont(self.main.small_font_size)
        self.third_label.setFont(self.main.small_font_size)
        self.create_label.setFont(self.main.small_font_size)
        self.test_entry.setFont(self.main.small_font_size)

        # Button Styling
        self.create_button.setFont(self.main.small_font_size)
        self.create_button.setFixedSize(self.main.small_button_size)

        # StyleSheet
        self.update_stylesheet()

        self.layout().invalidate()
        self.update()

    def update_stylesheet(self) -> None:
        """
        Update the widget stylesheet.

        Returns:
            None
        """
        self.setStyleSheet(f"""
            QPushButton {{
                padding: 5px
            }}""")
        
    def set_random_snippet(self) -> None:
        """
        Display a random snippet trigger in the instructional label.

        If no snippets exist, restores the default instructional message.

        Returns:
            None
        """
        snippet = self.main.snippet_db.get_random_snippet()
        if not snippet:
            label_text = (
                "Give your snippets a try below. "
                "It looks like you may want to create one to test here."
            )
            self.second_label.setText(label_text)
            return
        
        # Show trigger and snippet content
        msg = (
            "Give your snippets a try below. "
            f"Type <code>{snippet['trigger']}</code> now to see one in action."
        )
        self.second_label.setText(msg)

    def showEvent(self, event) -> None:
        """
        Handle widget show events.

        Refreshes the random snippet display and sets focus
        to the test entry field.

        Args:
            event (Any): The Qt show event.

        Returns:
            None
        """
        super().showEvent(event)
        self.set_random_snippet()   # Set random snippet on each load
        self.test_entry.setFocus(Qt.TabFocusReason) # Force focus when the form is shown
