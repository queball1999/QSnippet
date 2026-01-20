from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QSlider,
    QScrollArea, QVBoxLayout, QSpacerItem, QSizePolicy,
    QHBoxLayout
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

        # Adding save debounce
        self._emit_timers: dict[str, QTimer] = {}
        self.pending_values: dict[str, object] = {}

        self.initUI()

    def initUI(self):
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.header = QLabel(self.header_text())
        self.header.setObjectName("SettingsHeader")

        if self.parent_category:
            self.header.setCursor(Qt.PointingHandCursor)
            self.header.mousePressEvent = lambda _: self.dialog.pop_page()

        layout.addWidget(self.header)

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

            card = SettingsCard(
                title=title,
                description=description,
                control=control,
            )
            layout.addWidget(card)

            self.search_targets[key] = [
                (card, f"{title} {description}".lower())
            ]

        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Expanding))

    def header_text(self):
        if self.parent_category:
            return f"{self.parent_category} › {self.category}".replace("_", " ").title()
        return self.category.replace("_", " ").title()

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


    # ----- CONTROLS -----

    def emit_change(self, key: str, value, delay: int = 400):
        """
        Debounced change emitter.
        """
        self.pending_values[key] = value

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
