from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtCore import Qt

_EYE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="{stroke}" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>"""

_EYE_OFF_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
    fill="none" stroke="{stroke}" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
  <path d="m1 1 22 22"/>
  <path d="M10.73 10.73a3 3 0 0 0 4.01 4.48"/>
</svg>"""


def icon_stroke() -> str:
    """Return the active theme's icon colour, falling back to neutral grey."""
    try:
        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        return tm.icon_color() if tm else "#888888"
    except Exception:
        return "#888888"


def svg_icon(svg_template: str, stroke: str = None) -> QIcon:
    """Render an eye SVG in *stroke*, so the icon follows the active theme."""
    px = QPixmap()
    px.loadFromData(
        svg_template.format(stroke=stroke or icon_stroke()).encode("utf-8"), "SVG"
    )
    return QIcon(px)


def eye_icons() -> tuple[QIcon, QIcon]:
    """Return the (show, hide) reveal icons tinted for the active theme."""
    stroke = icon_stroke()
    return svg_icon(_EYE_SVG, stroke), svg_icon(_EYE_OFF_SVG, stroke)


class PasswordField(QLineEdit):
    """QLineEdit with a show/hide toggle action on the trailing edge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self.showing = False
        self.toggle_action = QAction("", self)
        self.toggle_action.setToolTip("Show password")
        self.addAction(self.toggle_action, QLineEdit.TrailingPosition)
        self.toggle_action.triggered.connect(self.toggle)

        # Setup keyboard toggle; scope it to this field so several password
        # fields in one window do not register an ambiguous shortcut.
        self.toggle_action.setShortcut(Qt.CTRL | Qt.Key_Space)
        self.toggle_action.setShortcutContext(Qt.WidgetShortcut)

        self.applyStyles()

    def applyStyles(self) -> None:
        """Re-render the reveal icons in the current theme's icon colour."""
        self.icon_on, self.icon_off = eye_icons()
        self.toggle_action.setIcon(self.icon_off if self.showing else self.icon_on)

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
