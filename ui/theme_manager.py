import logging
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme base palettes
# Accent-dependent keys (accent, accent_hover, border_focus, selected,
# highlight) are filled in at apply-time for "dark" and "light" so the
# Windows system accent color is always respected.
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    # Windows 11 File Explorer dark mode
    "dark": {
        "window":          "#202020",
        "panel":           "#2b2b2b",
        "card":            "rgba(255, 255, 255, 0.05)",
        "card_hover":      "rgba(255, 255, 255, 0.08)",
        "input":           "rgba(255, 255, 255, 0.06)",
        "hover":           "#393939",
        "text":            "#ffffff",
        "text_muted":      "rgba(255, 255, 255, 0.6)",
        # accent / accent_hover / border_focus / selected / highlight
        # > filled dynamically from system accent color
        "accent":          "#9c0000",          # fallback only
        "accent_hover":    "rgba(96,205,255,0.15)",
        "border_focus":    "#60cdff",
        "selected":        "#393939",
        "highlight":       "rgba(96,205,255,0.18)",
        "danger":          "#fc4f4f",
        "danger_hover":    "rgba(252, 79, 79, 0.15)",
        "border":          "rgba(255, 255, 255, 0.08)",
        "scrollbar":       "rgba(255, 255, 255, 0.18)",
        "scrollbar_hover": "rgba(255, 255, 255, 0.38)",
        "search_panel":    "#2b2b2b",
    },
    # Windows 11 light mode
    "light": {
        "window":          "#f3f3f3",
        "panel":           "#ffffff",
        "card":            "rgba(0, 0, 0, 0.04)",
        "card_hover":      "rgba(0, 0, 0, 0.08)",
        "input":           "#ffffff",
        "hover":           "#ececec",
        "text":            "#000000",
        "text_muted":      "rgba(0, 0, 0, 0.55)",
        # accent filled dynamically
        "accent":          "#0067c0",
        "accent_hover":    "#0067c01f",
        "border_focus":    "#0067c0",
        "selected":        "#ececec",
        "highlight":       "#0067c01f",
        "danger":          "#c42b1c",
        "danger_hover":    "rgba(196, 43, 28, 0.12)",
        "border":          "rgba(0, 0, 0, 0.08)",
        "scrollbar":       "rgba(0, 0, 0, 0.2)",
        "scrollbar_hover": "rgba(0, 0, 0, 0.38)",
        "search_panel":    "#ffffff",
    },
    # Nord palette - https://www.nordtheme.com/docs/colors-and-palettes
    # Polar Night: #2E3440 #3B4252 #434C5E #4C566A
    # Snow Storm:  #D8DEE9 #E5E9F0 #ECEFF4
    # Frost:       #8FBCBB #88C0D0 #81A1C1 #5E81AC
    # Aurora:      #BF616A #D08770 #EBCB8B #A3BE8C #B48EAD
    "nord": {
        "window":          "#2E3440",
        "panel":           "#3B4252",
        "card":            "#3B4252",
        "card_hover":      "#434C5E",
        "input":           "#4c566a",
        "hover":           "#434C5E",
        "text":            "#ECEFF4",
        "text_muted":      "rgba(216, 222, 233, 0.6)",
        "accent":          "#88C0D0",
        "accent_hover":    "rgba(136, 192, 208, 0.15)",
        "border_focus":    "#88C0D0",
        "selected":        "#434C5E",
        "highlight":       "rgba(136, 192, 208, 0.15)",
        "danger":          "#BF616A",
        "danger_hover":    "rgba(191, 97, 106, 0.15)",
        "border":          "rgba(76, 86, 106, 0.7)",
        "scrollbar":       "rgba(216, 222, 233, 0.2)",
        "scrollbar_hover": "rgba(216, 222, 233, 0.4)",
        "search_panel":    "#3B4252",
    },
    "pink": {
        "window":          "#fff0f7",
        "panel":           "#ffffff",
        "card":            "rgba(233, 30, 140, 0.05)",
        "card_hover":      "rgba(233, 30, 140, 0.09)",
        "input":           "#fff5fa",
        "hover":           "#fff5fa",
        "text":            "#5c1a3a",
        "text_muted":      "rgba(92, 26, 58, 0.55)",
        "accent":          "#e91e8c",
        "accent_hover":    "rgba(233, 30, 140, 0.12)",
        "border_focus":    "#e91e8c",
        "selected":        "#fff5fa",
        "highlight":       "rgba(233, 30, 140, 0.1)",
        "danger":          "#c62828",
        "danger_hover":    "rgba(198, 40, 40, 0.12)",
        "border":          "rgba(233, 30, 140, 0.2)",
        "scrollbar":       "rgba(233, 30, 140, 0.25)",
        "scrollbar_hover": "rgba(233, 30, 140, 0.45)",
        "search_panel":    "#ffffff",
    },
}

THEME_DISPLAY_NAMES = {
    "system": "System",
    "dark":   "Dark",
    "light":  "Light",
    "nord":   "Nord",
    "pink":   "Girly Pink",
}

# Themes that should inherit the Windows system accent color
_SYSTEM_ACCENT_THEMES = frozenset({"dark", "light"})
# Themes treated as visually dark (white icons)
_DARK_THEMES = frozenset({"dark", "nord"})


class ThemeManager(QObject):
    """
    Singleton that owns theme state and applies a global QApplication stylesheet.

    Usage:
        tm = ThemeManager(app)
        tm.apply("dark", scale_pct=100)

    After construction, retrieve the singleton via ThemeManager.instance().
    """

    themeChanged = Signal()

    _instance: "ThemeManager | None" = None

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._theme_name = "dark"
        self._scale_pct  = 100
        ThemeManager._instance = self

    @classmethod
    def instance(cls) -> "ThemeManager | None":
        return cls._instance

    # Public API

    def apply(self, theme_name: str, scale_pct: int = 100, accent_color: str = "system") -> None:
        """Resolve theme name, build QSS, and set it on QApplication."""
        resolved = self.resolve_theme(theme_name)
        self._theme_name = resolved
        self._scale_pct  = scale_pct

        colors = self.resolve_colors(resolved, accent_color)
        qss    = self.build_qss(colors, scale_pct)
        self.app.setStyleSheet(qss)
        self.apply_font_scale(scale_pct)
        self.force_repaint()
        self.update_animated_switches(colors["accent"])
        self.themeChanged.emit()
        logger.info("Theme applied: %s @ %d%%", resolved, scale_pct)

    def get_colors(self) -> dict[str, str]:
        return self.resolve_colors(self._theme_name)

    @property
    def is_dark(self) -> bool:
        return self._theme_name in _DARK_THEMES

    def icon_color(self) -> str:
        """Return the correct icon tint color for the current theme."""
        return "#ffffff" if self.is_dark else "#1c1c1c"

    def recolor_icon(self, icon: "QIcon", color: str) -> "QIcon":
        """
        Return a copy of *icon* tinted to *color* while preserving transparency.
        Uses SourceIn composition so the shape is kept but all color replaced.
        """
        from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon as _QIcon
        from PySide6.QtCore import QSize, Qt

        pixmap = QPixmap()
        for size in (32, 24, 16):
            pixmap = icon.pixmap(QSize(size, size))
            if not pixmap.isNull():
                break

        if pixmap.isNull():
            return icon

        result = QPixmap(pixmap.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), QColor(color))
        painter.end()
        return _QIcon(result)

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def scale_pct(self) -> int:
        return self._scale_pct

    def update_animated_switches(self, accent: str) -> None:
        """Push the new accent color into every live QAnimatedSwitch."""
        try:
            from ui.widgets import QAnimatedSwitch
            for w in self.app.allWidgets():
                if isinstance(w, QAnimatedSwitch):
                    w.update_accent(accent)
        except Exception as e:
            logger.warning("Switch accent update failed: %s", e)

    # System theme / accent detection
    def detect_system_theme(self) -> str:
        """Return 'dark' or 'light' based on the OS color scheme."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication
            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            pass

        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        except Exception:
            pass

        return "dark"

    def resolve_theme(self, name: str) -> str:
        if name == "system":
            return self.detect_system_theme()
        return name if name in THEMES else "dark"

    def get_system_accent(self, is_dark: bool) -> str:
        """
        Return the Windows system accent color as '#RRGGBB'.
        Falls back to a sensible default if the color cannot be read.
        """
        default_dark  = "#9c0000"
        default_light = "#9c0000"

        # Qt palette highlight color mirrors the Windows accent color
        try:
            from PySide6.QtGui import QGuiApplication
            color = QGuiApplication.palette().highlight().color()
            # palette().highlight() can return mid-gray on some platforms;
            # treat anything too desaturated as an unusable fallback
            if color.saturation() > 20:
                return color.name()          # '#RRGGBB'
        except Exception:
            pass

        # Direct Windows registry read (ABGR little-endian DWORD)
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\DWM",
            )
            value, _ = winreg.QueryValueEx(key, "AccentColor")
            r = value & 0xFF
            g = (value >> 8) & 0xFF
            b = (value >> 16) & 0xFF
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            pass

        return default_dark if is_dark else default_light

    def hex_to_rgba(self, hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

    def resolve_colors(self, theme_name: str, accent_override: str = "system") -> dict[str, str]:
        """Return the color dict, injecting the accent for dark/light themes."""
        c = dict(THEMES[theme_name])
        if theme_name in _SYSTEM_ACCENT_THEMES:
            is_dark = theme_name == "dark"
            if accent_override and accent_override.lower() != "system":
                accent = accent_override
            else:
                accent = self.get_system_accent(is_dark)
            c["accent"]       = accent
            c["accent_hover"] = self.hex_to_rgba(accent, 0.15)
            c["border_focus"] = accent
            c["highlight"]    = self.hex_to_rgba(accent, 0.18)
            # Light uses accent for selection; dark keeps its own #393939
            if not is_dark:
                c["selected"] = self.hex_to_rgba(accent, 0.15)
        return c

    def force_repaint(self) -> None:
        """
        Unpolish and re-polish every live widget so the new QSS takes effect.
        Also calls applyStyles() on any widget that implements it so explicit
        setFont() calls (e.g. SnippetTable) pick up the new scaled QFont objects.
        """
        style = self.app.style()
        for w in self.app.allWidgets():
            style.unpolish(w)
            style.polish(w)
            w.update()
            if hasattr(w, "applyStyles"):
                try:
                    w.applyStyles()
                except Exception:
                    pass

    # Font scale
    def apply_font_scale(self, scale_pct: int) -> None:
        from PySide6.QtGui import QFont
        base_pt = 10
        scaled  = max(7, round(base_pt * scale_pct / 100))
        font = self.app.font()
        font.setPointSize(scaled)
        self.app.setFont(font)

    # QSS generation
    def build_qss(self, c: dict, scale: int) -> str:
        s   = scale / 100.0
        r4  = max(2, round(4  * s))
        r6  = max(3, round(6  * s))
        r8  = max(4, round(8  * s))
        r12 = max(6, round(12 * s))
        p4  = max(2, round(4  * s))
        p6  = max(3, round(6  * s))
        p8  = max(4, round(8  * s))
        p10 = max(5, round(10 * s))
        p12 = max(6, round(12 * s))

        return f"""
/* Base */
QWidget {{
    background-color: {c['window']};
    color: {c['text']};
    selection-background-color: {c['selected']};
    selection-color: {c['text']};
}}

QMainWindow, QDialog {{
    background-color: {c['window']};
}}

QLabel {{
    background-color: transparent;
    color: {c['text']};
}}

QFrame {{
    background-color: transparent;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

/* Inputs */
QLineEdit {{
    background-color: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    padding: {p8}px;
    selection-background-color: {c['selected']};
}}
QLineEdit:focus {{
    border-color: {c['border_focus']};
}}

QTextEdit, QPlainTextEdit {{
    background-color: {c['input']};
    color: {c['text']};
    border: none;
    selection-background-color: {c['selected']};
}}

QSpinBox {{
    background-color: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
}}
QSpinBox:focus {{
    border-color: {c['border_focus']};
}}

/* ComboBox */
QComboBox {{
    background-color: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    selection-background-color: {c['selected']};
    padding: {p4}px {p6}px;
}}
QComboBox:focus {{
    border-color: {c['border_focus']};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: {p8}px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['panel']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    selection-background-color: {c['selected']};
    outline: none;
}}

/* Buttons */
QPushButton {{
    background-color: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    min-width: 20px;
    min-height: 12px;
    padding: {p4}px {p8}px;
}}
QPushButton:hover {{
    background-color: {c['hover']};
    border-color: {c['hover']};
}}
QPushButton:pressed {{
    background-color: {c['selected']};
}}
QPushButton:disabled {{
    color: {c['text_muted']};
    border-color: {c['border']};
}}

/* Checkboxes */
QCheckBox {{
    color: {c['text']};
    spacing: {p6}px;
}}
QCheckBox:disabled {{
    color: {c['text_muted']};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: {r4}px;
    border: 1px solid {c['border']};
}}
QCheckBox::indicator:unchecked {{
    background-color: {c['input']};
}}
QCheckBox::indicator:unchecked:hover {{
    background-color: {c['input']};
    border-color: {c['accent']};
}}
QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border: none;
    image: url(assets/icons/checkbox-checked-light.svg);
    padding: 2px;
}}
QCheckBox::indicator:checked:hover {{
    background-color: {c['accent']};
    border: none;
    image: url(assets/icons/checkbox-checked-light.svg);
}}
QCheckBox::indicator:checked:pressed {{
    background-color: {c['accent']};
    border: none;
    image: url(assets/icons/checkbox-checked-light.svg);
}}
QCheckBox::indicator:disabled {{
    background-color: {c['input']};
    border-color: {c['border']};
}}

/* Tree View */
QTreeView {{
    background-color: {c['window']};
    color: {c['text']};
    border: none;
    outline: none;
    alternate-background-color: {c['window']};
}}
QTreeView::item:selected {{
    background-color: {c['selected']};
    color: {c['text']};
}}
QTreeView::item:hover {{
    background-color: {c['hover']};
}}

QHeaderView::section {{
    background-color: {c['window']};
    color: {c['text']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: {p4}px {p8}px;
}}

/* List Widget */
QListWidget {{
    background-color: transparent;
    color: {c['text']};
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: {r6}px;
    color: {c['text']};
}}
QListWidget::item:selected {{
    background-color: {c['selected']};
    color: {c['text']};
}}
QListWidget::item:hover:!selected {{
    background-color: {c['hover']};
}}

QListWidget#SearchResultsList {{
    background-color: {c['search_panel']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
}}

/* Scroll Bars */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['scrollbar']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['scrollbar_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c['scrollbar']};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['scrollbar_hover']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Menus */
QMenu {{
    background-color: {c['panel']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    padding: {p4}px;
}}
QMenu::item {{
    padding: {p6}px {p12}px;
    border-radius: {r4}px;
}}
QMenu::item:selected {{
    background-color: {c['selected']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: {p4}px 0;
}}

QMenuBar {{
    background-color: {c['window']};
    color: {c['text']};
    border-bottom: 1px solid {c['border']};
}}
QMenuBar::item:selected {{
    background-color: {c['hover']};
    border-radius: {r4}px;
}}

/* Slider */
QSlider::groove:horizontal {{
    background: {c['border']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']};
    border-radius: 6px;
    width: 12px;
    height: 12px;
    margin: -4px 0;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    background: {c['panel']};
}}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    padding: {p6}px {p12}px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {c['text']};
    border-bottom: 2px solid {c['accent']};
}}

/* Tooltip */
QToolTip {{
    background-color: {c['panel']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
    padding: {p4}px {p6}px;
}}

/* Settings dialog color rules */
QLabel#SettingsCardDescription {{
    color: {c['text_muted']};
}}
QLabel#SettingsChevron {{
    color: {c['text_muted']};
}}
QLabel#SettingsLabel {{
    color: {c['text']};
}}
QLabel#SettingsLabel[highlighted="true"] {{
    background-color: {c['highlight']};
    border-radius: {r4}px;
    padding: 2px {p4}px;
}}
QLabel#SettingsHeader[highlighted="true"] {{
    color: {c['accent']};
}}

SettingsCard {{
    background-color: {c['card']};
}}
SettingsCard:hover {{
    background-color: {c['card_hover']};
}}
SettingsSubCategoryCard {{
    background-color: {c['card']};
}}
SettingsSubCategoryCard:hover {{
    background-color: {c['card_hover']};
}}
SettingsCard[highlighted="true"],
SettingsSubCategoryCard[highlighted="true"] {{
    background-color: {c['highlight']};
}}

QPushButton#SettingsResetBtn {{
    background: transparent;
    border: 1px solid {c['border']};
    color: {c['text_muted']};
    min-width: 0;
    min-height: 0;
    padding: 0px;
}}
QPushButton#SettingsResetBtn:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent']};
    color: {c['accent']};
}}

QPushButton#RestoreDefaultsBtn {{
    background: transparent;
    border: 1px solid {c['border']};
    color: {c['text_muted']};
}}
QPushButton#RestoreDefaultsBtn:hover {{
    background-color: {c['danger_hover']};
    border-color: {c['danger']};
    color: {c['danger']};
}}

/* Settings Dialog */
QListWidget {{
    border: none;
    font-size: {round(18 * s)}px;
}}
QListWidget#SearchResultsList {{
    font-size: {round(13 * s)}px;
}}
QListWidget::item {{
    padding: {p10}px {p12}px;
    border-radius: 6px;
}}
QLabel#SettingsHeader {{
    font-size: {round(26 * s)}px;
    font-weight: 600;
    padding-bottom: {p10}px;
}}
QLabel#SettingsLabel {{
    font-size: {round(14 * s)}px;
}}
QLabel#SettingsCardTitle {{
    font-size: {round(15 * s)}px;
    font-weight: 600;
}}
QLabel#SettingsCardDescription {{
    font-size: {round(12 * s)}px;
}}
QLabel#SettingsChevron {{
    font-size: {round(20 * s)}px;
}}
SettingsCard {{
    border-radius: 8px;
}}
SettingsSubCategoryCard {{
    border-radius: 8px;
}}
QPushButton#SettingsResetBtn {{
    width: 24px;
    height: 24px;
    min-width: 24px;
    min-height: 24px;
    max-width: 24px;
    max-height: 24px;
    border-radius: 12px;
    font-size: {round(14 * s)}px;
    padding: 0px;
}}
QPushButton#RestoreDefaultsBtn {{
    border-radius: 6px;
    padding: 8px 12px;
    font-size: {round(13 * s)}px;
}}
"""
