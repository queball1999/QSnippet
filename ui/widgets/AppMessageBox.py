from PySide6.QtWidgets import QMessageBox, QCheckBox
from PySide6.QtGui import QIcon



class AppMessageBox(QMessageBox):
    def __init__(self, icon_path=None, parent=None) -> None:
        """
        Initialize the AppMessageBox.

        Stores an optional window icon path for reuse across message dialogs.

        Args:
            icon_path (str | None): Path to the window icon.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self._icon_path = icon_path

    def setup(self, title, text, icon, buttons) -> int:
        """
        Configure the message box properties.

        Resets the dialog state and applies the provided title, text,
        icon type, and standard buttons.

        Args:
            title (str): The window title.
            text (str): The message text.
            icon (QMessageBox.Icon): The icon type to display.
            buttons (QMessageBox.StandardButtons): The buttons to show.

        Returns:
            None
        """
        self.setWindowIcon(QIcon(self._icon_path) if self._icon_path else QIcon())
        self.setWindowTitle(title)
        self.setText(text)
        self.setIcon(icon)
        self.setStandardButtons(buttons)

    def info(self, text, title="Info", buttons=QMessageBox.Ok) -> int:
        """
        Display an information message dialog.

        Args:
            text (str): The message text.
            title (str): The window title.
            buttons (QMessageBox.StandardButtons): The buttons to display.

        Returns:
            int: The standard button enum value clicked by the user.
        """
        self.setup(title, text, QMessageBox.Information, buttons)
        return self.exec()

    def warning(self, text, title="Warning", buttons=QMessageBox.Ok) -> int:
        """
        Display a warning message dialog.

        Args:
            text (str): The message text.
            title (str): The window title.
            buttons (QMessageBox.StandardButtons): The buttons to display.

        Returns:
            int: The standard button enum value clicked by the user.
        """
        self.setup(title, text, QMessageBox.Warning, buttons)
        return self.exec()

    def error(self, text, title="Error", buttons=QMessageBox.Ok) -> int:
        """
        Display an error message dialog.

        Args:
            text (str): The message text.
            title (str): The window title.
            buttons (QMessageBox.StandardButtons): The buttons to display.

        Returns:
            int: The standard button enum value clicked by the user.
        """
        self.setup(title, text, QMessageBox.Critical, buttons)
        return self.exec()

    def question(self, text, title="Question",
                 buttons=QMessageBox.Yes | QMessageBox.No,
                 default_button=QMessageBox.No) -> int:
        """
        Display a question dialog with configurable buttons.

        Args:
            text (str): The message text.
            title (str): The window title.
            buttons (QMessageBox.StandardButtons): The buttons to display.
            default_button (QMessageBox.StandardButton): The default selected button.

        Returns:
            int: The standard button enum value clicked by the user.
        """
        self.setup(title, text, QMessageBox.Question, buttons)
        self.setDefaultButton(default_button)
        return self.exec()
    
    def notice(self, 
               text: str, 
               title: str = "Notice", 
               checkbox_text: str = "Never show again") -> bool:
        """
        Display a notice dialog with an optional "Never show again" checkbox.

        Args:
            text (str): The notice message text.
            title (str): The window title.
            checkbox_text (str): The label for the checkbox.

        Returns:
            bool: True if the checkbox was checked, otherwise False.
        """
        box = QMessageBox()
        box.setWindowIcon(QIcon(self._icon_path) if self._icon_path else QIcon())
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.Ok)

        self.setCheckBox(None)
        checkbox = QCheckBox(checkbox_text)
        box.setCheckBox(checkbox)

        box.exec()
        return checkbox.isChecked()
    
    def showEvent(self, event) -> None:
        """
        Handle the show event to enforce a minimum dialog size.

        Args:
            event (Any): The Qt show event.

        Returns:
            None
        """
        super().showEvent(event)
        self.resize(max(self.width(), 500), max(self.height(), 250))
