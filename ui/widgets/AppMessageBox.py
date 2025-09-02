from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QIcon

class AppMessageBox(QMessageBox):
    def __init__(self, icon_path=None, parent=None):
        super().__init__(parent)
        self._icon_path = icon_path

    def _setup(self, title, text, icon, buttons):
        # Reset state so we don't carry over previous calls
        self.setWindowIcon(QIcon(self._icon_path) if self._icon_path else QIcon())
        self.setWindowTitle(title)
        self.setText(text)
        self.setIcon(icon)
        self.setStandardButtons(buttons)

    def info(self, text, title="Info", buttons=QMessageBox.Ok):
        self._setup(title, text, QMessageBox.Information, buttons)
        return self.exec()

    def warning(self, text, title="Warning", buttons=QMessageBox.Ok):
        self._setup(title, text, QMessageBox.Warning, buttons)
        return self.exec()

    def error(self, text, title="Error", buttons=QMessageBox.Ok):
        self._setup(title, text, QMessageBox.Critical, buttons)
        return self.exec()

    def question(self, text, title="Question",
                 buttons=QMessageBox.Yes | QMessageBox.No,
                 default_button=QMessageBox.No):
        self._setup(title, text, QMessageBox.Question, buttons)
        self.setDefaultButton(default_button)
        return self.exec()