from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QTimer


class SettingsToast(QLabel):
    def __init__(self, parent):
        super().__init__("Saved", parent)

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setObjectName("SettingsToast")
        self.setAlignment(Qt.AlignCenter)

        self.setStyleSheet("""
            QLabel#SettingsToast {
                background-color: #00cc6a;
                color: white;
                padding: 8px 14px;
                border-radius: 6px;
                font-size: 13px;
            }
        """)

        self.hide()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_toast(self, duration_ms: int = 1200):
        """ Show the toast for a specified duration in milliseconds """
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

        self._hide_timer.start(duration_ms)

    def _reposition(self):
        """ Move the toast to the top-right corner of the parent """
        parent = self.parentWidget()
        if not parent:
            return

        margin = 16
        x = parent.width() - self.width() - margin
        y = margin
        self.move(x, y)
