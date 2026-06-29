from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtCore import Qt

_EYE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="#888888" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>"""

_EYE_OFF_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="#888888" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
  <path d="m1 1 22 22"/>
  <path d="M10.73 10.73a3 3 0 0 0 4.01 4.48"/>
</svg>"""


def svg_icon(svg_bytes: bytes) -> QIcon:
    px = QPixmap()
    px.loadFromData(svg_bytes, "SVG")
    return QIcon(px)


class PasswordField(QLineEdit):
    """QLineEdit with a show/hide toggle action on the trailing edge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self.showing = False
        self.icon_on = svg_icon(_EYE_SVG)
        self.icon_off = svg_icon(_EYE_OFF_SVG)
        self.toggle_action = QAction(self.icon_on, "", self)
        self.toggle_action.setToolTip("Show password")
        self.addAction(self.toggle_action, QLineEdit.TrailingPosition)
        self.toggle_action.triggered.connect(self.toggle)

    def toggle(self) -> None:
        self.showing = not self.showing
        if self.showing:
            self.setEchoMode(QLineEdit.Normal)
            self.toggle_action.setIcon(self.icon_off)
            self.toggle_action.setToolTip("Hide password")
        else:
            self.setEchoMode(QLineEdit.Password)
            self.toggle_action.setIcon(self.icon_on)
            self.toggle_action.setToolTip("Show password")
