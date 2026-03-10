from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QSlider,
    QScrollArea, QVBoxLayout, QSpacerItem, QSizePolicy,
    QHBoxLayout, QPushButton, QFrame
)
from PySide6.QtCore import Qt, QTimer

from ui.widgets import QAnimatedSwitch
from .settings_card import SettingsCard
from .settings_subcategory_card import SettingsSubCategoryCard


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
        self._controls: dict[str, tuple[QWidget, QPushButton, dict]] = {}

        # Adding save debounce
        self._emit_timers: dict[str, QTimer] = {}
        self.pending_values: dict[str, object] = {}

        self.initUI()

    def initUI(self):
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)    # Remove border
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(0)
        self._build_breadcrumb(self.header_layout)
        self.header_layout.addStretch()

        layout.addLayout(self.header_layout)

        for key, meta in self.values.items():
            title = key.replace("_", " ").title()

            # Ignore invalid nodes
            if not isinstance(meta, dict):
                continue

            # Skip if element is hidden
            if meta.get("hidden", False):
                continue

            # Sub-category
            if "value" not in meta:
                card = SettingsSubCategoryCard(title=title, key=key)
                card.clicked.connect(self.open_subcategory)
                layout.addWidget(card)

                self.search_targets[key] = [(card, title.lower())]
                continue

            # Leaf Settings
            description = meta.get("description", "")
            control = self.create_widget(key, meta)

            # Create reset button (visible only when value != default)
            reset_btn = self.create_reset_button(key, meta)
            self._controls[key] = (control, reset_btn, meta)

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

    def _build_breadcrumb(self, layout: QHBoxLayout):
        """
        Build clickable breadcrumb labels from self.path.
        Each ancestor is clickable and navigates back to that depth.
        The current (last) segment is non-clickable.
        """
        depth = len(self.path)

        for i, segment in enumerate(self.path):
            is_last = (i == depth - 1)
            title = segment.replace("_", " ").title()

            label = QLabel(title)
            label.setObjectName("SettingsHeader")

            if not is_last:
                # Clickable ancestor - pops back to this depth
                pops_needed = depth - 1 - i
                label.setCursor(Qt.PointingHandCursor)
                label.mousePressEvent = lambda _, n=pops_needed: self.dialog.pop_pages(n)

            layout.addWidget(label)

            if not is_last:
                separator = QLabel(" › ")
                separator.setObjectName("SettingsHeader")
                layout.addWidget(separator)

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
        btn = QPushButton("↺")
        btn.setObjectName("SettingsResetBtn")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("Restore default")
        btn.clicked.connect(lambda: self.reset_setting(key))

        has_default = "default" in meta
        is_changed = has_default and meta.get("value") != meta.get("default")
        btn.setVisible(is_changed)

        return btn

    def update_reset_visibility(self, key: str, current_value):
        """ Show or hide the reset button based on whether value differs from default. """
        if key not in self._controls:
            return

        _, reset_btn, meta = self._controls[key]
        has_default = "default" in meta
        is_changed = has_default and current_value != meta.get("default")
        reset_btn.setVisible(is_changed)

    def reset_setting(self, key: str):
        """ Reset a single setting to its default value. """
        if key not in self._controls:
            return

        control, reset_btn, meta = self._controls[key]
        default = meta.get("default")

        if default is None:
            return

        # Update the control widget (this triggers the change signal automatically)
        self._set_control_value(control, meta, default)
        reset_btn.setVisible(False)

    def _set_control_value(self, control: QWidget, meta: dict, value):
        """ Programmatically set a control widget's value. """
        typ = meta.get("type")

        if typ == "bool" and isinstance(control, QAnimatedSwitch):
            control.setChecked(bool(value))
            return

        if isinstance(control, QComboBox):
            control.setCurrentText(str(value))
            return

        if typ == "int":
            # Container widget with slider + label
            slider = control.findChild(QSlider)
            if slider:
                slider.setValue(int(value))
            return

        if isinstance(control, QLineEdit):
            control.setText(str(value))
            return

    def reset_all_to_defaults(self):
        """
        Reset all leaf settings on this page (and sub-categories) to defaults.
        Returns True if any value was actually changed.
        """
        changed = False

        for key, (control, reset_btn, meta) in self._controls.items():
            if "default" not in meta:
                continue
            if meta.get("value") == meta.get("default"):
                continue

            self._set_control_value(control, meta, meta["default"])
            reset_btn.setVisible(False)
            changed = True

        return changed

    # ----- CONTROLS -----

    def emit_change(self, key: str, value, delay: int = 400):
        """
        Debounced change emitter.
        """
        self.pending_values[key] = value
        self.update_reset_visibility(key, value)

        if key not in self._emit_timers:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self.flush_change(k))
            self._emit_timers[key] = timer

        timer = self._emit_timers[key]
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
        value = meta.get("value")
        options = meta.get("options")
        type = meta.get("type")

        if type == "bool":
            w = QAnimatedSwitch()
            w.setChecked(bool(value))
            w.stateChanged.connect(lambda v: self.emit_change(key, v))
            return w

        if options:
            w = QComboBox()
            w.addItems([str(o) for o in options])
            w.setCurrentText(str(value))
            w.setMinimumWidth(100)
            w.currentTextChanged.connect(lambda v: self.emit_change(key, v))
            return w

        if type == "int":
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(meta.get("min", 0))
            slider.setMaximum(meta.get("max", 100))
            slider.setValue(int(value))

            value_label = QLabel(str(value))
            value_label.setFixedWidth(40)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            slider.valueChanged.connect(
                lambda v: (
                    value_label.setText(str(v)),
                    self.emit_change(key, v)
                )
            )

            row.addWidget(slider, 1)
            row.addWidget(value_label)

            return container

        w = QLineEdit(str(value))
        w.textChanged.connect(lambda v: self.emit_change(key, v))
        return w
