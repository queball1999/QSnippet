from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QSlider,
    QScrollArea, QVBoxLayout, QSpacerItem, QSizePolicy,
    QHBoxLayout, QPushButton, QFrame, QStyledItemDelegate
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QPainter, QIcon

from utils.file_utils import FileUtils
from ui.widgets import QAnimatedSwitch
from .settings_card import SettingsCard
from .settings_subcategory_card import SettingsSubCategoryCard


class FontItemDelegate(QStyledItemDelegate):
    """Renders each font name in its own font."""

    def paint(self, painter: QPainter, option, index) -> None:
        font_name = index.data(Qt.DisplayRole)
        if font_name:
            font = QFont(font_name, 10)
            option.font = font
        super().paint(painter, option, index)


class SettingsCategoryPage(QWidget):
    def __init__(self, category: str, values: dict, on_change, parent_category=None, parent_page=None, parent=None):
        super().__init__(parent)

        self.category = category
        self.parent_category = parent_category
        self.path = parent_page.path + [category] if parent_page else [category]

        self.dialog = parent
        self.values = values if isinstance(values, dict) else {}
        self.on_change = on_change
        self.search_targets = {}

        # Track controls for reset: {key: (control_widget, reset_btn, meta)}
        self.controls: dict[str, tuple[QWidget, QPushButton, dict]] = {}

        # Adding save debounce
        self.emit_timers: dict[str, QTimer] = {}
        self.pending_values: dict[str, object] = {}
        self.breadcrumb_labels: list[QLabel] = []

        self.initUI()

    def get_main_app(self):
        """Get reference to main QSnippet app instance."""
        try:
            # dialog.parent() = QSnippet window (Qt method on SettingsDialog)
            # window.parent  = Python attribute on QSnippet = main() app instance
            window = self.dialog.parent()
            return getattr(window, 'parent', None)
        except Exception:
            pass
        return None

    def apply_widget_font(self, widget: QWidget, font_size: str = "medium"):
        """Apply appropriate font to a widget based on type."""
        if not widget:
            return

        app = self.get_main_app()
        if not app:
            return

        font_attr = f"{font_size}_font_size"
        if hasattr(app, font_attr):
            font = getattr(app, font_attr)
            widget.setFont(font)

    def apply_breadcrumb_font(self, label: QLabel):
        """Apply breadcrumb font: bold and one size smaller than previous extra-large."""
        app = self.get_main_app()
        if not app:
            return

        if hasattr(app, "large_font_size_bold"):
            label.setFont(getattr(app, "large_font_size_bold"))
            return

        # Fallback when bold variant is unavailable
        if hasattr(app, "large_font_size"):
            font = getattr(app, "large_font_size")
            font.setBold(True)
            label.setFont(font)

    def initUI(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(0)
        self.build_breadcrumb(self.header_layout)
        self.header_layout.addStretch()

        layout.addLayout(self.header_layout)

        for key, meta in self.values.items():
            title = key.replace("_", " ").title()

            # Ignore invalid nodes
            if not isinstance(meta, dict):
                continue

            # Skip metadata keys injected by normalize_settings
            if key == "description":
                continue

            # Skip if element is hidden
            if meta.get("hidden", False):
                continue

            # Sub-category
            if "value" not in meta:
                description = meta.get("description", "")
                if isinstance(description, dict):
                    description = description.get("value", "")
                card = SettingsSubCategoryCard(title=title, key=key, description=description)
                card.clicked.connect(self.open_subcategory)
                layout.addWidget(card)

                self.search_targets[key] = [(card, f"{title} {description}".lower())]
                continue

            # Leaf Settings
            description = meta.get("description", "")
            control = self.create_widget(key, meta)

            # Create reset button (visible only when value != default)
            reset_btn = self.create_reset_button(key, meta)
            self.controls[key] = (control, reset_btn, meta)

            card = SettingsCard(
                title=title,
                description=description,
                control=control,
                reset_btn=reset_btn,
            )
            layout.addWidget(card)

            self.search_targets[key] = [
                (card, f"{title} {description}".lower())
            ]

        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Expanding))

    def build_breadcrumb(self, layout: QHBoxLayout):
        """
        Build clickable breadcrumb labels from self.path.
        Each ancestor is clickable and navigates back to that depth.
        The current (last) segment is non-clickable.
        """
        depth = len(self.path)
        self.breadcrumb_labels.clear()

        for i, segment in enumerate(self.path):
            is_last = (i == depth - 1)
            title = segment.replace("_", " ").title()

            label = QLabel(title)
            label.setObjectName("SettingsHeader")
            self.apply_breadcrumb_font(label)
            self.breadcrumb_labels.append(label)

            if not is_last:
                # Clickable ancestor - pops back to this depth
                pops_needed = depth - 1 - i
                label.setCursor(Qt.PointingHandCursor)
                label.mousePressEvent = lambda _, n=pops_needed: self.dialog.pop_pages(n)

            layout.addWidget(label)

            if not is_last:
                separator = QLabel(" › ")
                separator.setObjectName("SettingsHeader")
                self.apply_breadcrumb_font(separator)
                self.breadcrumb_labels.append(separator)
                layout.addWidget(separator)

    def refresh_breadcrumb_fonts(self):
        """Re-apply current breadcrumb fonts, including already-rendered root labels."""
        for label in self.breadcrumb_labels:
            if label is not None:
                self.apply_breadcrumb_font(label)

    # ----- SEARCH -----

    def apply_search_highlight(self, search: str):
        search = search.lower().strip()

        for items in self.search_targets.values():
            for widget, text in items:
                widget.setProperty("highlighted", bool(search and search in text))
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def scroll_to_first_match(self, search: str):
        search = search.lower().strip()

        scroll_area = self.findChild(QScrollArea)
        if not scroll_area:
            return

        for items in self.search_targets.values():
            for widget, text in items:
                if search in text:
                    scroll_area.ensureWidgetVisible(widget, 0, 20)
                    return


    # ----- NAV -----

    def open_subcategory(self, key: str):
        """ Open a sub-category page. """
        sub = self.values.get(key)
        if not isinstance(sub, dict):
            return

        page = SettingsCategoryPage(
            category=key,
            values=sub,
            on_change=self.on_change,
            parent=self.dialog,
            parent_category=self.category,
            parent_page=self,
        )
        self.dialog.push_page(page)


    # ----- RESET -----

    def create_reset_button(self, key: str, meta: dict) -> QPushButton:
        """
        Create a small reset button for a setting.
        Visible only when current value differs from the default.
        """
        btn = QPushButton()
        btn.setObjectName("SettingsResetBtn")
        btn.setFixedSize(24, 24)
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("Restore default")
        btn.clicked.connect(lambda: self.reset_setting(key))
        self.apply_reset_button_icon(btn)

        has_default = "default" in meta
        is_changed = has_default and meta.get("value") != meta.get("default")
        btn.setVisible(is_changed)

        return btn

    def apply_reset_button_icon(self, btn: QPushButton) -> None:
        """ Tint the reset button's undo icon to match the current theme. """
        from ui.theme_manager import ThemeManager
        icon = QIcon(FileUtils.icon_path("undo-arrow.svg"))
        tm = ThemeManager.get_instance()
        if tm:
            icon = tm.recolor_icon(icon, tm.icon_color())
        btn.setIcon(icon)

    def applyStyles(self) -> None:
        """ Re-tint reset button icons when the theme changes. """
        for _, reset_btn, _ in self.controls.values():
            self.apply_reset_button_icon(reset_btn)

    def update_reset_visibility(self, key: str, current_value):
        """ Show or hide the reset button based on whether value differs from default. """
        if key not in self.controls:
            return

        _, reset_btn, meta = self.controls[key]
        has_default = "default" in meta
        is_changed = has_default and current_value != meta.get("default")
        reset_btn.setVisible(is_changed)

    def reset_setting(self, key: str):
        """ Reset a single setting to its default value. """
        if key not in self.controls:
            return

        control, reset_btn, meta = self.controls[key]
        default = meta.get("default")

        if default is None:
            return

        # Update the control widget
        self.set_control_value(control, meta, default)
        reset_btn.setVisible(False)

        # Emit the change so settings are persisted and theme is re-applied if needed
        self.emit_change(key, default)

    def set_control_value(self, control: QWidget, meta: dict, value):
        """ Programmatically set a control widget's value. """
        from ui.widgets.color_picker_widget import ColorPickerWidget
        typ     = meta.get("type", "string")
        element = (meta.get("element") or "").lower()

        control.blockSignals(True)

        # Color picker
        if element == "colorpicker" and isinstance(control, ColorPickerWidget):
            control.set_value(str(value))
            control.blockSignals(False)
            return

        # Bool toggle
        if typ in ("bool", "boolean") and isinstance(control, QAnimatedSwitch):
            control.setChecked(bool(value))
            control.blockSignals(False)
            return

        if isinstance(control, QComboBox):
            control.setCurrentText(str(value))
            control.blockSignals(False)
            return

        # Integer slider container
        if typ in ("int", "integer"):
            slider = control.findChild(QSlider)
            if slider:
                slider.blockSignals(True)
                slider.setValue(int(value))
                slider.blockSignals(False)
                # Also sync the value label sitting next to the slider
                lbl = control.findChild(QLabel)
                if lbl:
                    lbl.setText(str(int(value)))
            control.blockSignals(False)
            return

        if isinstance(control, QLineEdit):
            control.setText(str(value))
            control.blockSignals(False)
            return

        control.blockSignals(False)

    def reset_all_to_defaults(self):
        """
        Reset all leaf settings on this page (and sub-categories) to defaults.
        Returns True if any value was actually changed.
        """
        changed = False

        for key, (control, reset_btn, meta) in self.controls.items():
            if "default" not in meta:
                continue
            if meta.get("value") == meta.get("default"):
                continue

            self.set_control_value(control, meta, meta["default"])
            reset_btn.setVisible(False)
            changed = True

        return changed

    # ----- CONTROLS -----

    def emit_change(self, key: str, value, delay: int = 400):
        """
        Debounced change emitter.
        """
        control, _, meta = self.controls.get(key, (None, None, {}))
        old_value = meta.get("value")
        full_path = self.path + [key]

        if control and hasattr(self.dialog, "approve_setting_change"):
            approved = self.dialog.approve_setting_change(full_path, old_value, value)
            if not approved:
                self.set_control_value(control, meta, old_value)
                return

        self.pending_values[key] = value
        self.update_reset_visibility(key, value)

        if key not in self.emit_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self.flush_change(k))
            self.emit_timers[key] = timer

        timer = self.emit_timers[key]
        timer.start(delay)

    def flush_change(self, key: str):
        """ Flush changes for a specific key. """
        if key not in self.pending_values:
            return

        value = self.pending_values.pop(key)
        full_path = self.path + [key]
        self.on_change(full_path, value)

    def create_widget(self, key, meta):
        """ Create a control widget based on metadata. """
        value   = meta.get("value")
        options = meta.get("options")
        typ     = meta.get("type", "string")
        element = (meta.get("element") or "").lower()

        # --- Color picker ---
        if element == "colorpicker":
            from ui.widgets.color_picker_widget import ColorPickerWidget
            w = ColorPickerWidget(str(value) if value is not None else "system")
            w.setMinimumWidth(160)
            self.apply_widget_font(w)
            w.colorChanged.connect(lambda v: self.emit_change(key, v))
            return w

        # --- Bool toggle ---
        if typ in ("bool", "boolean"):
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.get_instance()
            accent = tm.get_colors()["accent"] if tm else "#4fa3ff"
            w = QAnimatedSwitch(checked_color=accent)
            w.setChecked(bool(value))
            w.stateChanged.connect(lambda v: self.emit_change(key, v))
            return w

        # --- Options → combobox ---
        if options:
            w = QComboBox()
            w.addItems([str(o) for o in options])
            w.setCurrentText(str(value))
            w.setMinimumWidth(100)

            # Apply font-specific rendering for font_family
            if key == "font_family":
                w.setItemDelegate(FontItemDelegate())

            self.apply_widget_font(w)
            w.currentTextChanged.connect(lambda v: self.emit_change(key, v))
            return w

        # --- Integer (slider, spinbox, or fallback line-edit) ---
        if typ in ("int", "integer"):
            if element == "slider":
                container = QWidget()
                container.setStyleSheet("background-color: transparent;")
                row = QHBoxLayout(container)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(8)

                slider = QSlider(Qt.Horizontal)
                slider.setMinimum(meta.get("min", 0))
                slider.setMaximum(meta.get("max", 100))
                slider.setValue(int(value))
                slider.setMinimumWidth(120)

                value_label = QLabel(str(value))
                value_label.setFixedWidth(36)
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.apply_widget_font(value_label)

                slider.valueChanged.connect(
                    lambda v: (
                        value_label.setText(str(v)),
                        self.emit_change(key, v),
                    )
                )

                row.addWidget(slider, 1)
                row.addWidget(value_label)
                return container

            if element == "spinbox":
                from PySide6.QtWidgets import QSpinBox
                spinbox = QSpinBox()
                spinbox.setMinimum(meta.get("min", 0))
                spinbox.setMaximum(meta.get("max", 100))
                spinbox.setValue(int(value))
                spinbox.setMinimumWidth(80)
                spinbox.setSingleStep(1)
                spinbox.setFocusPolicy(Qt.StrongFocus)
                self.apply_widget_font(spinbox)
                spinbox.valueChanged.connect(lambda v: self.emit_change(key, v))
                return spinbox

            # Default: line-edit for integers
            w = QLineEdit(str(value))
            self.apply_widget_font(w)
            w.textChanged.connect(lambda v: self.emit_change(key, v))
            return w

        # --- Fallback: plain text ---
        w = QLineEdit(str(value))
        self.apply_widget_font(w)
        w.textChanged.connect(lambda v: self.emit_change(key, v))
        return w
