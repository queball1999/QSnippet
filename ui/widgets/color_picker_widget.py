from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


class ColorPickerWidget(QWidget):
    """
    Compact swatch + label that opens a QColorDialog when clicked.

    Emits colorChanged(str) with '#RRGGBB' or 'system' whenever the value
    changes.  The swatch always reflects the *effective* accent for the
    current theme (pink/nord show their built-in accent; dark/light show the
    system or custom color).
    """

    colorChanged = Signal(str)

    def __init__(self, value: str = "system", parent=None):
        super().__init__(parent)
        self._value = value if value else "system"
        self._system_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(36, 24)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.setToolTip("Click to choose a color")
        self.swatch.clicked.connect(self.open_picker)

        self.label = QLabel()
        self.label.setObjectName("SettingsCardDescription")

        layout.addWidget(self.swatch)
        layout.addWidget(self.label)
        layout.addStretch()

        self.refresh()

        # Refresh whenever the theme changes so the swatch stays in sync
        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.instance()
            if tm:
                tm.themeChanged.connect(self.refresh)
        except Exception:
            pass

    # Public interface
    def get_value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value if value else "system"
        self.refresh()

    # Internal helpers
    def display_color(self) -> str:
        """Return the effective hex color for the current context."""
        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.instance()
            if tm:
                # Pink / Nord always use their own built-in accent
                if tm.theme_name not in ("dark", "light"):
                    return tm.get_colors()["accent"]
                # Dark / Light with "system" value → resolve from OS
                if self._value.lower() == "system":
                    return tm.get_system_accent(tm.is_dark)
        except Exception:
            pass

        if self._value.lower() == "system":
            return "#4fa3ff"
        return self._value

    def refresh(self) -> None:
        color = self.display_color()
        qc = QColor(color)
        brightness = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
        border = "rgba(0,0,0,0.35)" if brightness > 128 else "rgba(255,255,255,0.35)"

        self.swatch.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 2px solid {border};
                border-radius: 4px;
                min-width: 0;
                min-height: 0;
                padding: 0px;
            }}
        """)

        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.instance()
            is_fixed_theme = tm and tm.theme_name not in ("dark", "light")
        except Exception:
            is_fixed_theme = False

        if is_fixed_theme:
            self.label.setText("Theme default")
        elif self._value.lower() == "system":
            self.label.setText("System default")
        else:
            self.label.setText(self._value)

    def open_picker(self) -> None:
        from PySide6.QtWidgets import QColorDialog, QDialogButtonBox
        from PySide6.QtGui import QColor

        # If on pink/nord, the accent is fixed — nothing to pick
        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.instance()
            if tm and tm.theme_name not in ("dark", "light"):
                return
        except Exception:
            pass

        self._system_selected = False

        dialog = QColorDialog(QColor(self.display_color()), self)
        dialog.setWindowTitle("Choose Accent Color")
        # DontUseNativeDialog lets us inject the extra button
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)

        btn_box = dialog.findChild(QDialogButtonBox)
        if btn_box:
            sys_btn = btn_box.addButton(
                "Use System Color", QDialogButtonBox.ButtonRole.ResetRole
            )
            sys_btn.clicked.connect(lambda: self.pick_system(dialog))

        if dialog.exec() and not self._system_selected:
            color = dialog.selectedColor()
            if color.isValid():
                self._value = color.name()
                self.refresh()
                self.colorChanged.emit(self._value)

    def pick_system(self, dialog) -> None:
        """Called when the user clicks 'Use System Color' in the dialog."""
        self._system_selected = True
        self._value = "system"
        self.refresh()
        self.colorChanged.emit("system")
        dialog.accept()
