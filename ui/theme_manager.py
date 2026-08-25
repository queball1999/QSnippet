import logging
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon

from utils.file_utils import FileUtils

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
        # #393939 (same as "hover") is nearly invisible here: QTextEdit/
        # QLineEdit's "input" background is a translucent white (6%) over
        # the panel, which composites to ~#383838 - almost identical to
        # #393939, so selected text showed no visible highlight.
        "selected":        "#585858",
        "highlight":       "rgba(96,205,255,0.18)",
        "danger":          "#fc4f4f",
        "danger_hover":    "rgba(252, 79, 79, 0.15)",
        "border":          "rgba(255, 255, 255, 0.08)",
        "scrollbar":       "rgba(255, 255, 255, 0.18)",
        "scrollbar_hover": "rgba(255, 255, 255, 0.38)",
        "warning":         "#ffc107",
        "warning_bg":      "rgba(255, 193, 7, 0.12)",
        "warning_text":    "#ffd75e",
        "success":         "#6cc46c",
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
        "warning":         "#ffc107",
        "warning_bg":      "#fff3cd",
        "warning_text":    "#664d03",
        "success":         "#157347",
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
        "warning":         "#EBCB8B",
        "warning_bg":      "rgba(235, 203, 139, 0.14)",
        "warning_text":    "#EBCB8B",
        "success":         "#A3BE8C",
        "search_panel":    "#3B4252",
    },
    "pink": {
        "window":          "#fff0f7",
        "panel":           "#ffffff",
        "card":            "rgba(233, 30, 140, 0.05)",
        "card_hover":      "rgba(233, 30, 140, 0.09)",
        "input":           "#ffffff",
        "hover":           "#f8dae9",
        "text":            "#5c1a3a",
        "text_muted":      "rgba(92, 26, 58, 0.55)",
        "accent":          "#f752ad",
        "accent_hover":    "rgba(233, 30, 140, 0.12)",
        "border_focus":    "#f752ad",
        "selected":        "#fff5fa",
        "highlight":       "rgba(233, 30, 140, 0.1)",
        "danger":          "#c62828",
        "danger_hover":    "rgba(198, 40, 40, 0.12)",
        "border":          "rgba(233, 30, 140, 0.2)",
        "scrollbar":       "rgba(233, 30, 140, 0.25)",
        "scrollbar_hover": "rgba(233, 30, 140, 0.45)",
        "warning":         "#e0a800",
        "warning_bg":      "rgba(224, 168, 0, 0.14)",
        "warning_text":    "#7a5c00",
        "success":         "#2e7d32",
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

# ---------------------------------------------------------------------------
# Role fonts keyed by objectName.
#
# objectName is already the styling contract used by build_qss(); this table
# extends the same contract to font sizing so a widget's typography is decided
# in exactly one place instead of being re-derived by each dialog's applyStyles.
# Values are (size_role, bold). Anything not listed gets ("medium", False).
# ---------------------------------------------------------------------------
OBJECT_NAME_FONTS: dict[str, tuple[str, bool]] = {
    # Settings
    "SettingsHeader":            ("large",  True),
    "SettingsChevron":           ("large",  False),
    "SettingsCardTitle":         ("medium", True),
    "SettingsCardDescription":   ("small",  False),
    "SettingsToast":             ("medium", False),
    # Vault dialogs
    "VaultDialogTitle":          ("large",  True),
    "VaultDialogDesc":           ("small",  False),
    "VaultFieldLabel":           ("medium", True),
    "VaultField":                ("medium", False),
    "VaultErrorLabel":           ("small",  False),
    "VaultHintPass":             ("small",  False),
    "VaultHintFail":             ("small",  False),
    "VaultRecoveryCode":         ("large",  True),
    "VaultWarningText":          ("small",  False),
    "VaultOptionsNote":          ("small",  False),
    "VaultOptionsSectionTitle":  ("medium", True),
    "VaultRecoveryLink":         ("small",  False),
    "VaultHintLabel":            ("small",  False),
    "VaultConfirmCheck":         ("small",  False),
    "VaultHeaderTitle":          ("large",  True),
    "VaultHeaderDesc":           ("small",  False),
    "VaultStatusPill":           ("small",  False),
    # Import / export wizard
    "ImportExportTitle":         ("large",  True),
    # Update dialog
    "UpdateDialogTitle":         ("large",  True),
    "CountLabel":                ("small",  False),
    # Backups
    "BackupPageBtn":             ("small",  False),
    "BackupPageBtnCurrent":      ("small",  True),
    "BackupPageSize":            ("small",  False),
    # Placeholder dialog
    "PanelTitle":                ("large",  True),
    "FieldLabel":                ("large",  False),
    "FieldHint":                 ("small",  False),
    "ErrorLabel":                ("small",  False),
    "SystemNotice":              ("small",  False),
    # Snippet popout
    "PopoutSnippetName":         ("large",  True),
    "PopoutLabel":               ("medium", False),
    # Notice carousel
    "NoticeTopLabel":            ("large",  True),
    "NoticeTitleLabel":          ("medium", True),
    # Tutorial overlay
    "TutorialTitle":             ("large",  True),
    "TutorialBody":              ("medium", False),
    "TutorialProgress":          ("small",  False),
    "TutorialBtn":               ("medium", False),
    "TutorialNextBtn":           ("medium", True),
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

    After construction, retrieve the singleton via ThemeManager.get_instance().
    """

    themeChanged = Signal()

    instance: "ThemeManager | None" = None

    def __init__(self, app, main=None):
        super().__init__()
        self.app = app
        self.main = main
        self.theme_name = "dark"
        self.scale_pct  = 100
        ThemeManager.instance = self

    @classmethod
    def get_instance(cls) -> "ThemeManager | None":
        return cls.instance

    @classmethod
    def app_instance(cls):
        """
        Return the main() application object that owns the scaled QFont
        attributes (small_font_size, medium_font_size, ...).

        This is the single supported way for any widget to reach those fonts.
        Widgets must never walk the Qt/Python parent chain themselves: the
        QSnippet window stores its owner on a Python attribute named `parent`
        that shadows QWidget.parent(), so hand-rolled walks silently fail
        depending on how deeply a widget happens to be nested.
        """
        tm = cls.instance
        return getattr(tm, "main", None) if tm else None

    @classmethod
    def font(cls, size: str = "medium", bold: bool = False):
        """
        Return a scaled QFont by role name ("small", "medium", "large",
        "extra_large", "humongous"), falling back to the QApplication font
        when the main app is not reachable (e.g. isolated widget tests).
        """
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication

        app = cls.app_instance()
        if app is not None:
            attr = f"{size}_font_size" + ("_bold" if bold else "")
            font = getattr(app, attr, None)
            if font is not None:
                # Hand back a copy; callers (and Qt) must never mutate the
                # shared QFont objects owned by the main app.
                return QFont(font)
            font = getattr(app, f"{size}_font_size", None)
            if font is not None:
                font = QFont(font)
                font.setBold(bold)
                return font

        qapp = QApplication.instance()
        font = QFont(qapp.font()) if qapp else QFont()
        font.setBold(bold)
        return font

    @classmethod
    def toggle_size(cls, size: str = "small"):
        """Return the scaled QSize for a QAnimatedSwitch toggle, or None."""
        app = cls.app_instance()
        return getattr(app, f"{size}_toggle_size", None) if app else None

    @classmethod
    def font_for(cls, widget, default_size: str = "medium"):
        """Return the scaled QFont for *widget* based on its objectName role."""
        try:
            name = widget.objectName()
        except RuntimeError:
            name = ""
        size, bold = OBJECT_NAME_FONTS.get(name, (default_size, False))
        return cls.font(size, bold)

    @classmethod
    def apply_fonts(cls, root, default_size: str = "medium") -> None:
        """
        Apply role-correct scaled fonts to *root* and every text-bearing widget
        beneath it, using OBJECT_NAME_FONTS.

        This is the shared implementation behind every dialog's applyStyles():
        call it instead of hand-rolling per-widget setFont() loops, so a new
        object name only has to be registered once to be styled everywhere.
        """
        from PySide6.QtWidgets import (
            QWidget, QLabel, QLineEdit, QComboBox, QSpinBox, QTextEdit,
            QPlainTextEdit, QPushButton, QCheckBox, QRadioButton,
            QAbstractItemView, QHeaderView,
        )

        applicable = (
            QLabel, QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit,
            QPushButton, QCheckBox, QRadioButton, QAbstractItemView,
        )

        def apply_one(w):
            try:
                if isinstance(w, applicable):
                    font = cls.font_for(w, default_size)
                    w.setFont(font)
                    if isinstance(w, QComboBox) and w.lineEdit():
                        w.lineEdit().setFont(font)
                    if isinstance(w, QAbstractItemView):
                        w.viewport().update()
                if isinstance(w, QHeaderView):
                    w.setFont(cls.font(default_size))
                    w.viewport().update()
            except RuntimeError:
                pass
            except Exception:
                pass

        try:
            apply_one(root)
            # findChildren with a tuple of types crashes PySide6; filter here.
            for child in root.findChildren(QWidget):
                apply_one(child)
        except RuntimeError:
            pass
        except Exception as e:
            logger.debug("apply_fonts failed for %r: %s", root, e)

    # Public API

    def apply(self, theme_name: str, scale_pct: int = 100, accent_color: str = "system", btn_pad_x: int = 8, btn_pad_y: int = 6) -> None:
        """Resolve theme name, build QSS, and set it on QApplication."""
        resolved = self.resolve_theme(theme_name)
        self.theme_name = resolved
        self.scale_pct  = scale_pct
        self.btn_pad_x  = btn_pad_x
        self.btn_pad_y  = btn_pad_y

        colors = self.resolve_colors(resolved, accent_color)
        qss    = self.build_qss(colors, scale_pct, btn_pad_x, btn_pad_y)
        self.app.setStyleSheet(qss)
        self.apply_font_scale(scale_pct)
        self.force_repaint()
        self.update_animated_switches(colors["accent"], colors)
        self.themeChanged.emit()
        logger.info("Theme applied: %s @ %d%%", resolved, scale_pct)

    def get_colors(self) -> dict[str, str]:
        return self.resolve_colors(self.theme_name)

    @property
    def is_dark(self) -> bool:
        return self.theme_name in _DARK_THEMES

    def icon_color(self) -> str:
        """Return the correct icon tint color for the current theme."""
        return "#ffffff" if self.is_dark else "#1c1c1c"

    def icon_qss_url(self, name: str) -> str:
        """
        Return a QSS-safe `url(...)` value for assets/icons/<name>, resolved
        against the PyInstaller resource dir (bundled) or working dir (dev/
        portable) so the path is valid inside a packaged build.
        """
        path = FileUtils.icon_path(name).replace("\\", "/")
        return f"url({path})"

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

    def update_animated_switches(self, accent: str, colors: dict | None = None) -> None:
        """Push the new accent color into every live QAnimatedSwitch."""
        try:
            from ui.widgets import QAnimatedSwitch
            try:
                from shiboken6 import isValid as is_valid
            except Exception:
                is_valid = None

            for w in list(self.app.allWidgets()):
                try:
                    if is_valid and not is_valid(w):
                        continue
                    if isinstance(w, QAnimatedSwitch):
                        w.update_accent(accent)
                except RuntimeError:
                    continue
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

    @classmethod
    def qcolor(cls, key: str, fallback: str = "#808080"):
        """
        Return a palette entry as a QColor.

        Palette values may be hex ("#ffffff") or CSS rgba with a float alpha
        ("rgba(255, 255, 255, 0.6)"). QColor cannot parse the latter, so it is
        converted here; use this instead of QColor(colors[key]) anywhere a
        palette colour is needed for painting rather than for QSS.
        """
        from PySide6.QtGui import QColor

        tm = cls.instance
        value = tm.get_colors().get(key, fallback) if tm else fallback
        value = str(value).strip()

        if value.startswith("rgb"):
            try:
                parts = value[value.index("(") + 1:value.rindex(")")].split(",")
                r, g, b = (int(float(x)) for x in parts[:3])
                a = int(float(parts[3]) * 255) if len(parts) > 3 else 255
                return QColor(r, g, b, a)
            except Exception:
                return QColor(fallback)

        color = QColor(value)
        return color if color.isValid() else QColor(fallback)

    def contrast_text(self, color: str) -> str:
        """
        Return black or white, whichever stays readable on top of *color*.
        Used for text painted directly on the accent (toast, primary buttons),
        which would otherwise be invisible against a pale system accent.
        """
        try:
            from PySide6.QtGui import QColor
            qc = QColor(color)
            if not qc.isValid():
                return "#ffffff"
            luminance = (0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue())
            return "#000000" if luminance > 150 else "#ffffff"
        except Exception:
            return "#ffffff"

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
        # Readable foreground for anything painted directly on the accent
        c["on_accent"] = self.contrast_text(c["accent"])
        return c

    def force_repaint(self) -> None:
        """
        Re-apply every style surface, in the only order that produces a
        consistent result:

          1. repolish_all()        - re-evaluate the new QSS on every widget
          2. apply_app_fonts()     - blanket sweep that pushes the medium font
                                     (and, crucially, the new font family) onto
                                     every generic widget
          3. refresh_widget_styles() - per-widget applyStyles()/refresh_fonts()
                                     hooks that restore role-specific sizes
                                     (titles, hints, counters, headers, ...)

        Phase 2 must run before phase 3. It deliberately overwrites every
        widget font, so any hook that ran before it would have its
        role-specific sizes stomped straight back to medium.
        """
        self.repolish_all()
        self.apply_app_fonts()
        self.refresh_widget_styles()

    def live_widgets(self) -> list:
        """
        Snapshot every live widget up front so object churn during a repaint
        cannot invalidate the iterator, and drop wrappers whose underlying C++
        object has already been destroyed.
        """
        try:
            from shiboken6 import isValid as is_valid
        except Exception:
            is_valid = None

        widgets = []
        for w in list(self.app.allWidgets()):
            if w is None:
                continue
            try:
                if is_valid and not is_valid(w):
                    continue
            except RuntimeError:
                continue
            widgets.append(w)
        return widgets

    def repolish_all(self) -> None:
        """Unpolish and re-polish every live widget so the new QSS takes effect."""
        style = self.app.style()
        for w in self.live_widgets():
            try:
                style.unpolish(w)
                style.polish(w)
                w.update()
            except RuntimeError:
                continue
            except Exception:
                continue

    def apply_app_fonts(self) -> None:
        """
        Run the main app's blanket font sweep, which pushes the current font
        family/size onto widgets that never call setFont() themselves
        (status bars, group boxes, tab bars, header views, ...).
        """
        app = self.app_instance()
        sweep = getattr(app, "apply_fonts_to_all_widgets", None) if app else None
        if callable(sweep):
            try:
                sweep()
            except Exception as e:
                logger.debug("Blanket font sweep failed: %s", e)

    def refresh_widget_styles(self) -> None:
        """
        Call applyStyles()/refresh_fonts() on every live widget that implements
        them, so explicit setFont() calls and per-theme icon tints are restored
        after the blanket sweep.
        """
        for w in self.live_widgets():
            for hook_name in ("applyStyles", "refresh_fonts"):
                try:
                    hook = getattr(w, hook_name, None)
                except RuntimeError:
                    break

                if callable(hook):
                    try:
                        hook()
                    except RuntimeError:
                        break
                    except Exception:
                        pass

    # Font scale
    def apply_font_scale(self, scale_pct: int) -> None:
        """
        Set the application font.

        This is the only font the widgets outside apply_fonts' reach ever
        get: QMenuBar, the popup QMenus, QToolBar and the tray menu all
        inherit it rather than being visited by the sweep.

        It must be the app's own scaled "medium" role, which already folds
        in the screen ratio and the user's UI scale. This used to compute a
        second size of its own from a fixed 10pt base, which disagreed with
        the medium role; the menu bar and toolbar latched onto that other
        number and so came back a size bigger than they started whenever
        the scale was raised and put back to 100%.

        The fixed base survives only as a fallback for when the main app
        object isn't reachable, such as an isolated widget test.

        Args:
            scale_pct (int): The user's UI scale percentage.

        Returns:
            None
        """
        from PySide6.QtGui import QFont

        app = self.app_instance()
        medium = getattr(app, "medium_font_size", None) if app else None

        if medium is not None:
            # Hand Qt a copy; the main app's QFont objects are shared
            self.app.setFont(QFont(medium))
            return

        base_pt = 10
        scaled  = max(7, round(base_pt * scale_pct / 100))
        font = self.app.font()
        font.setPointSize(scaled)
        self.app.setFont(font)

    # QSS generation
    def build_qss(self, c: dict, scale: int, btn_pad_x: int = 8, btn_pad_y: int = 6) -> str:
        arrow_variant = "white" if self.is_dark else "dark"
        spinbox_up_icon   = self.icon_qss_url(f"spinbox-arrow-up-{arrow_variant}.svg")
        spinbox_down_icon = self.icon_qss_url(f"spinbox-arrow-down-{arrow_variant}.svg")
        checkbox_icon     = self.icon_qss_url("checkbox-checked-light.svg")
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
        bp_x = max(0, round(btn_pad_x * s))
        bp_y = max(0, round(btn_pad_y * s))

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
    padding-right: 2px;
}}
QSpinBox:focus {{
    border-color: {c['border_focus']};
}}
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    background-color: {c['input']};
    border-left: 1px solid {c['border']};
}}
QSpinBox::up-button:hover {{
    background-color: {c['hover']};
}}
QSpinBox::up-button:pressed {{
    background-color: {c['selected']};
}}
QSpinBox::up-arrow {{
    image: {spinbox_up_icon};
    width: 7px;
    height: 7px;
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    background-color: {c['input']};
    border-left: 1px solid {c['border']};
    border-top: 1px solid {c['border']};
}}
QSpinBox::down-button:hover {{
    background-color: {c['hover']};
}}
QSpinBox::down-button:pressed {{
    background-color: {c['selected']};
}}
QSpinBox::down-arrow {{
    image: {spinbox_down_icon};
    width: 7px;
    height: 7px;
}}

/* ComboBox */
QComboBox {{
    background-color: {c['input']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    selection-background-color: {c['selected']};
    padding: {p8}px {p6}px;
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
    min-height: 15px;
    padding: {bp_y}px {bp_x}px;
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
    image: {checkbox_icon};
    padding: 2px;
}}
QCheckBox::indicator:checked:hover {{
    background-color: {c['accent']};
    border: none;
    image: {checkbox_icon};
}}
QCheckBox::indicator:checked:pressed {{
    background-color: {c['accent']};
    border: none;
    image: {checkbox_icon};
}}
QCheckBox::indicator:disabled {{
    background-color: {c['input']};
    border-color: {c['border']};
}}

/* Tree View */
QTreeView {{
    background-color: {c['window']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r8}px;
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
    background-color: {c['hover']};
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
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    background: transparent;
    border: none;
    width: 0;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    background: transparent;
    border: none;
    height: 0;
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
/* The base ::item rule has to exist. Styling only ::item:selected leaves the
   normal state on Qt's built-in metrics and the hovered state on the
   stylesheet box model, so entries visibly grew as the mouse crossed them. */
QMenuBar::item {{
    background: transparent;
    color: {c['text']};
    padding: {p4}px {p8}px;
    margin: 0px;
    border: none;
    border-radius: {r4}px;
}}
QMenuBar::item:selected {{
    background-color: {c['hover']};
}}
QMenuBar::item:pressed {{
    background-color: {c['selected']};
}}
QMenuBar::item:disabled {{
    color: {c['text_muted']};
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
}}
QListWidget::item {{
    padding: {p10}px {p12}px;
    border-radius: 6px;
}}
QLabel#SettingsHeader {{
    font-weight: 700;
    padding-bottom: {p10}px;
}}
QLabel#SettingsCardTitle {{
    font-weight: 600;
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
    padding: 0px;
}}
QPushButton#RestoreDefaultsBtn {{
    border-radius: 6px;
    padding: 8px 12px;
}}

/* Snippet popout dialog */
QLabel#PopoutSnippetName {{
    font-weight: 700;
}}
QLabel#PopoutLabel {{
    color: {c['text_muted']};
}}

/* Snippet popout button */
QPushButton#PopoutBtn {{
    background: transparent;
    border: none;
    min-width: 0;
    min-height: 0;
    padding: 4px;
}}
QPushButton#PopoutBtn:hover {{
    background-color: {c['hover']};
    border-radius: {r4}px;
}}
QPushButton#PopoutBtn:pressed {{
    background-color: {c['selected']};
    border-radius: {r4}px;
}}

/* Reveal/hide buttons for encrypted content (snippet form, placeholder dialog) */
QPushButton#RevealSnippetBtn, QPushButton#RevealValueBtn, QPushButton#UnlockVaultBtn {{
    background: transparent;
    border: none;
    min-width: 0;
    min-height: 0;
    padding: 4px;
}}
QPushButton#RevealSnippetBtn:hover, QPushButton#RevealValueBtn:hover, QPushButton#UnlockVaultBtn:hover {{
    background-color: {c['hover']};
    border-radius: {r4}px;
}}
QPushButton#RevealSnippetBtn:pressed, QPushButton#RevealValueBtn:pressed, QPushButton#UnlockVaultBtn:pressed {{
    background-color: {c['selected']};
    border-radius: {r4}px;
}}

/* Vault dialogs */
QLabel#VaultDialogTitle {{
    font-weight: 700;
    padding-bottom: {p4}px;
}}
QLabel#VaultDialogDesc {{
    color: {c['text_muted']};
}}
QLabel#VaultErrorLabel {{
    color: {c['danger']};
    font-weight: 600;
    padding-top: {p4}px;
}}
QFrame#VaultWarningBox {{
    background-color: {c['warning_bg']};
    border: 1px solid {c['warning']};
    border-radius: {r4}px;
}}
QLabel#VaultWarningText {{
    color: {c['warning_text']};
}}
/* Primary action. Geometry is inherited from the base QPushButton rule so it
   matches every other button in the app; only the accent fill is added. */
QPushButton#VaultConfirmBtn {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
    font-weight: 600;
}}
QPushButton#VaultConfirmBtn:hover {{
    background-color: {c['accent']};
    border-color: {c['text']};
}}
QPushButton#VaultConfirmBtn:pressed {{
    background-color: {c['accent']};
    border-color: {c['on_accent']};
}}
QPushButton#VaultConfirmBtn:disabled {{
    background-color: {c['border']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}
/* Destructive action, styled like the primary but in the danger colour */
QPushButton#VaultDangerBtn {{
    background-color: {c['danger']};
    color: #ffffff;
    border: 1px solid {c['danger']};
    font-weight: 600;
}}
QPushButton#VaultDangerBtn:hover {{
    background-color: {c['danger']};
    border-color: {c['text']};
}}
QPushButton#VaultDangerBtn:disabled {{
    background-color: {c['border']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}
/* Page header block, matching the card surfaces used elsewhere */
QFrame#VaultHeader {{
    background-color: {c['card']};
    border: 1px solid {c['border']};
    border-radius: {r8}px;
}}
QLabel#VaultHeaderTitle {{
    font-weight: 700;
}}
QLabel#VaultHeaderDesc {{
    color: {c['text_muted']};
}}
QLabel#VaultStatusPill {{
    color: {c['text_muted']};
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
    padding: {p4}px {p8}px;
}}
QFrame#VaultSeparator {{
    color: {c['border']};
}}
QLineEdit#VaultField {{
    border: 1px solid {c['border']};
    border-radius: {r4}px;
    padding: {p4}px {p8}px;
    background-color: {c['input']};
    color: {c['text']};
}}
QLabel#VaultFieldLabel {{
    font-weight: 600;
}}
QLabel#VaultRecoveryCode {{
    font-family: monospace;
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 2px;
    padding: {p8}px;
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
}}
QFrame#VaultHintsFrame {{
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
}}
QLabel#VaultHintPass {{
    color: {c['success']};
}}
QLabel#VaultHintFail {{
    color: {c['text_muted']};
}}

/* Placeholder dialog */
QLabel#PanelTitle {{
    font-weight: bold;
    padding-bottom: {p4}px;
}}
QLabel#FieldLabel {{
    font-weight: bold;
}}
QLabel#FieldHint {{
    color: {c['text_muted']};
}}
QLabel#ErrorLabel {{
    color: {c['danger']};
}}
QLabel#SystemNotice {{
    color: {c['text_muted']};
    background-color: {c['panel']};
    border-radius: {r4}px;
    padding: {p6}px;
}}

/* Notice carousel */
QLabel#NoticeTopLabel {{
    font-weight: bold;
}}
QLabel#NoticeTitleLabel {{
    font-weight: bold;
}}

/* Import / export wizard */
QLabel#CountLabel {{
    color: {c['text_muted']};
    margin-left: 12px;
}}
QFrame#VaultOptionsFrame {{
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: {r4}px;
}}
QLabel#VaultOptionsNote {{
    color: {c['text_muted']};
}}

/* Vault link-style labels */
QLabel#VaultRecoveryLink {{
    color: {c['accent']};
}}
QLabel#VaultHintLabel {{
    color: {c['text_muted']};
}}

/* Platform notice banner (Linux) */
QWidget#PlatformNotice {{
    background: {c['warning_bg']};
    border: 1px solid {c['warning']};
    border-radius: {r4}px;
    padding: 5px;
}}
QWidget#PlatformNotice QLabel {{
    background: transparent;
    color: {c['warning_text']};
}}
QPushButton#PlatformNoticeClose {{
    background: transparent;
    border: none;
    color: {c['warning_text']};
    min-width: 0;
    min-height: 0;
    padding: 0px;
    font-weight: bold;
}}
QPushButton#PlatformNoticeClose:hover {{
    background: {c['hover']};
    border-radius: {r4}px;
}}

/* Backup history table */
QTableWidget#BackupHistoryTable {{
    background-color: transparent;
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r6}px;
    gridline-color: {c['border']};
    outline: none;
}}
QTableWidget#BackupHistoryTable::item {{
    padding: {p6}px {p8}px;
    border-bottom: 1px solid {c['border']};
}}
QTableWidget#BackupHistoryTable QHeaderView::section {{
    background-color: {c['card']};
    color: {c['text_muted']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: {p6}px {p8}px;
}}

/* Inline row action buttons */
QPushButton#BackupRowBtn {{
    background: transparent;
    border: none;
    min-width: 0;
    min-height: 0;
    padding: 2px;
    border-radius: {r4}px;
}}
QPushButton#BackupRowBtn:hover {{
    background-color: {c['hover']};
}}
QPushButton#BackupRowBtn:pressed {{
    background-color: {c['selected']};
}}
QPushButton#BackupRowBtn:disabled {{
    background: transparent;
}}

/* Pagination */
QPushButton#BackupPageBtn {{
    background: transparent;
    border: 1px solid {c['border']};
    color: {c['text']};
    min-width: 0;
    min-height: 0;
    padding: 0px {p6}px;
    border-radius: {r4}px;
}}
QPushButton#BackupPageBtn:hover {{
    background-color: {c['hover']};
    border-color: {c['accent']};
}}
QPushButton#BackupPageBtnCurrent {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
    min-width: 0;
    min-height: 0;
    padding: 0px {p6}px;
    border-radius: {r4}px;
}}
QPushButton#BackupPageBtnCurrent:disabled {{
    background-color: {c['accent']};
    color: {c['on_accent']};
}}

/* Tutorial overlay coach mark */
QWidget#TutorialOverlay {{
    background: transparent;
}}
QFrame#TutorialBubble {{
    background-color: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: {r12}px;
}}
QFrame#TutorialBubble QLabel {{
    background: transparent;
}}
QLabel#TutorialTitle {{
    color: {c['accent']};
}}
QLabel#TutorialBody {{
    color: {c['text']};
}}
QLabel#TutorialProgress {{
    color: {c['text_muted']};
}}
/* Back and Skip inherit the base QPushButton geometry, so they follow the
   user's button padding and the UI scale like every other button. Only the
   primary action adds the accent fill on top. */
QPushButton#TutorialNextBtn {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
}}
QPushButton#TutorialNextBtn:hover {{
    background-color: {c['accent']};
    border-color: {c['text']};
}}
QPushButton#TutorialNextBtn:pressed {{
    background-color: {c['accent']};
    border-color: {c['on_accent']};
}}
QPushButton#TutorialReplayBtn, QPushButton#TutorialCloseBtn {{
    background: transparent;
    border: none;
    min-width: 0;
    min-height: 0;
    padding: 2px;
    border-radius: {r4}px;
}}
QPushButton#TutorialReplayBtn:hover, QPushButton#TutorialCloseBtn:hover {{
    background-color: {c['hover']};
}}
QPushButton#TutorialReplayBtn:pressed, QPushButton#TutorialCloseBtn:pressed {{
    background-color: {c['selected']};
}}

/* Settings toast */
QLabel#SettingsToast {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    padding: {p8}px {p12}px;
    border-radius: {r6}px;
}}
"""
