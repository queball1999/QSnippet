from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QListWidget, QStackedWidget, QHBoxLayout,
    QListWidgetItem, QVBoxLayout, QLineEdit, QWidget
)
from PySide6.QtCore import Qt, QTimer

from .settings_category_page import SettingsCategoryPage
from .settings_toast import SettingsToast

# Object to hold search result data
@dataclass
class SearchResult:
    category: str
    path: list[str]
    label: str
    text: str


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, save_callback, parent=None):
        super().__init__(parent)
        self.toast = SettingsToast(self)

        self.settings = settings
        self.save_callback = save_callback
        self._last_sidebar_row = -1
        self._nav_stack: list[QWidget] = []
        self._search_index: list[SearchResult] = []

        # Adding search debounce timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(100)  # 0.1 seconds
        self.search_timer.timeout.connect(self.run_search)
        self.pending_search = ""

        self.setWindowTitle("Settings")
        self.resize(900, 600)

        self.initUI()
        self.build_search_index()

    def initUI(self):
        root = QHBoxLayout(self)

        # Left
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        left_container = QWidget()
        left_container.setLayout(left)
        left_container.setFixedWidth(260)

        self.search = QLineEdit(clearButtonEnabled=True)
        self.search.setFixedWidth(220)
        self.search.setPlaceholderText("Find a setting")
        self.search.textChanged.connect(self.on_search_text_changed)

        self.list = QListWidget()
        self.list.setFixedWidth(220)
        self.list.setFocusPolicy(Qt.NoFocus)

        left.addWidget(self.search)
        left.addWidget(self.list)

        # Search dropdown
        self.search_results = QListWidget(self)
        self.search_results.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
        )
        self.search_results.setAttribute(Qt.WA_ShowWithoutActivating)
        self.search_results.setFocusPolicy(Qt.NoFocus)
        self.search_results.itemClicked.connect(self.on_search_result_clicked)

        # Right
        self.stack = QStackedWidget()

        root.addWidget(left_container)
        root.addWidget(self.stack)

        self.build()
        self.list.itemClicked.connect(self.on_sidebar_changed)
        self.list.setCurrentRow(0)

        self.update_stylesheet()

    # ----- BUILD -----

    def build(self):
        """ Build the sidebar and root pages. """
        self.list.clear()

        for category, values in self.settings.items():
            self.list.addItem(QListWidgetItem(category.replace("_", " ").title()))

            page = SettingsCategoryPage(
                category=category,
                values=values,
                on_change=self.on_setting_changed,
                parent=self,
            )
            self.stack.addWidget(page)

    def build_search_index(self):
        """ Build the search index for all settings. """
        self._search_index.clear()

        def walk(category, node, path):
            for key, value in node.items():
                new_path = path + [key]

                if isinstance(value, dict) and "value" in value:
                    label = key.replace("_", " ").title()
                    desc = value.get("description", "")
                    text = f"{label} {desc}".lower()

                    self._search_index.append(
                        SearchResult(
                            category=category,
                            path=new_path,
                            label=label,
                            text=text,
                        )
                    )
                elif isinstance(value, dict):
                    walk(category, value, new_path)

        for category, values in self.settings.items():
            walk(category, values, [category])

    # ----- SEARCH -----

    def on_search_text_changed(self, text: str):
        """ Handle when the search text changes. """
        self.pending_search = text

        if not text.strip():
            self.search_timer.stop()
            self.search_results.hide()
            self.reset_navigation()
            return

        self.search_timer.start()

    def run_search(self):
        """ Process the search after debounce. """
        text = (self.pending_search or "").lower().strip()

        if not text:
            self.search_results.hide()
            self.reset_navigation()
            return

        matches = [r for r in self._search_index if text in r.text][:15]

        if not matches:
            self.search_results.hide()
            return

        self.search_results.clear()
        for r in matches:
            item = QListWidgetItem(f"{r.label} - {r.category.replace('_',' ').title()}")
            item.setData(Qt.UserRole, r)
            self.search_results.addItem(item)

        pos = self.search.mapToGlobal(self.search.rect().bottomLeft())
        self.search_results.move(pos)
        self.search_results.resize(self.search.width(), 240)
        self.search_results.show()

    def on_search_result_clicked(self, item: QListWidgetItem):
        """ Handle when a search result is clicked. """
        result: SearchResult = item.data(Qt.UserRole)
        self.search_results.hide()

        page, leaf_key = self.navigate_to_parent(result.path)
        page.apply_search_highlight(leaf_key.replace("_", " ").lower())
        page.scroll_to_first_match(leaf_key.replace("_", " ").lower())


    # ----- NAVIGATION -----

    def navigate_to_path(self, path: list[str]):
        """
        Navigate to the full path of a setting.
        Returns the final page widget.
        """
        self._nav_stack.clear()

        category = path[0]
        index = list(self.settings.keys()).index(category)

        self.list.setCurrentRow(index)
        page = self.stack.widget(index)
        self.stack.setCurrentWidget(page)

        for key in path[1:]:
            page = SettingsCategoryPage(
                category=key,
                values=page.values.get(key, {}),
                on_change=self.on_setting_changed,
                parent=self,
                parent_category=page.category,
            )
            self.push_page(page)

        return page
    
    def navigate_to_parent(self, path: list[str]):
        """
        Navigate only to the parent category of a leaf setting.
        Returns (page, leaf_key)
        """
        self._nav_stack.clear()

        category = path[0]
        index = list(self.settings.keys()).index(category)

        self.list.setCurrentRow(index)
        page = self.stack.widget(index)
        self.stack.setCurrentWidget(page)

        # walk only up to the parent of the leaf
        for key in path[1:-1]:
            page = SettingsCategoryPage(
                category=key,
                values=page.values.get(key, {}),
                on_change=self.on_setting_changed,
                parent=self,
                parent_category=page.category,
                parent_page=page,
            )
            self.push_page(page)

        leaf_key = path[-1]
        return page, leaf_key

    def push_page(self, page: QWidget):
        """ Add a new page to the navigation stack. """
        current = self.stack.currentWidget()
        if current:
            self._nav_stack.append(current)

        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def pop_page(self):
        """ Remove the current page and go back to the previous one. """
        if not self._nav_stack:
            return

        current = self.stack.currentWidget()
        previous = self._nav_stack.pop()

        self.stack.setCurrentWidget(previous)
        self.stack.removeWidget(current)
        current.deleteLater()

    def reset_navigation(self, select_row=0):
        """ Reset navigation to a specific root page. """
        self._nav_stack.clear()
        self.stack.setCurrentIndex(select_row)
        self.list.setCurrentRow(select_row)

        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            page.apply_search_highlight("")

    def on_sidebar_changed(self, item: QListWidgetItem):
        """ Handle when the user clicks a sidebar item """
        row = self.list.row(item)

        # If user clicked the same root again, reset navigation and return
        if row == self._last_sidebar_row:
            self.reset_navigation(row)
            return

        self._last_sidebar_row = row

        # Clear deep navigation
        self._nav_stack.clear()

        # Remove all stacked sub-pages (keep root pages only)
        root_count = len(self.settings)
        while self.stack.count() > root_count:
            widget = self.stack.widget(self.stack.count() - 1)
            self.stack.removeWidget(widget)
            widget.deleteLater()

        # Navigate to root page
        self.stack.setCurrentIndex(row)

    # ----- SETTINGS -----

    def on_setting_changed(self, path: list[str], value):
        """ Handle when a setting value changes. """
        node = self.settings

        for key in path[:-1]:
            node = node.setdefault(key, {})

        leaf = path[-1]

        if isinstance(node.get(leaf), dict):
            node[leaf]["value"] = value
        else:
            node[leaf] = value  # safety fallback

        if callable(self.save_callback):
            self.save_callback(self.settings)
            self.toast.show_toast()


    def update_stylesheet(self):
        """ Update the dialog's stylesheet. """
        
        self.setStyleSheet("""
        QComboBox {
            padding: 8px 12px;
        }
                           
        QLineEdit {
            padding: 8px;
        }

        QListWidget {
            background: transparent;
            border: none;
            font-size: 18px;
        }

        QListWidget::item {
            padding: 10px 12px;
            border-radius: 6px;
        }

        QListWidget::item:selected {
            background-color: rgba(79, 163, 255, 0.15);
        }

        QLabel#SettingsHeader {
            font-size: 26px;
            font-weight: 600;
            padding-bottom: 10px;
        }

        QLabel#SettingsLabel {
            font-size: 14px;
        }
                           
        QLabel#SettingsHeader[highlighted="true"] {
            color: rgba(79, 163, 255, 0.15);
        }

        QLabel#SettingsLabel[highlighted="true"] {
            background-color: rgba(79, 163, 255, 0.15);
            border-radius: 4px;
            padding: 2px 4px;
        }
                           
        SettingsCard {
            border-radius: 8px;
        }

        QLabel#SettingsCardTitle {
            font-size: 15px;
            font-weight: 600;
        }

        QLabel#SettingsCardDescription {
            font-size: 12px;
        }

        SettingsSubCategoryCard {
            border-radius: 8px;
        }

        SettingsSubCategoryCard:hover {
            background-color: rgba(79, 163, 255, 0.15);
        }
                           
        SettingsCard[highlighted="true"],
        SettingsSubCategoryCard[highlighted="true"] {
            background-color: rgba(79, 163, 255, 0.18);
        }

        QLabel#SettingsChevron {
            font-size: 20px;
            color: rgba(255, 255, 255, 0.4);
        }
        """)