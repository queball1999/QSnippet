from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QListWidget, QStackedWidget, QHBoxLayout,
    QListWidgetItem, QVBoxLayout, QLineEdit, QWidget,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtGui import QShortcut

from .settings_category_page import SettingsCategoryPage
from .settings_toast import SettingsToast


class TextEditFocusFilter(QObject):
    """
    Event filter to handle focus loss on text edit widgets.
    
    Clears selection and deselects text when focus is lost.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            if isinstance(obj, QLineEdit):
                obj.deselect()
        return super().eventFilter(obj, event)

# Object to hold search result data
@dataclass
class SearchResult:
    category: str
    path: list[str]
    label: str
    text: str


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, save_callback, parent=None, extra_pages=None):
        super().__init__(parent)
        self.toast = SettingsToast(self)

        self.settings = settings
        self.save_callback = save_callback
        self.last_sidebar_row = -1
        self.nav_stack: list[QWidget] = []
        self.search_index: list[SearchResult] = []
        self.extra_pages: list[tuple] = extra_pages or []
        self.extra_page_widgets: list[QWidget] = []

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
        self.applyStyles()


    def initUI(self):
        root = QHBoxLayout(self)

        # Left
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left_container = QWidget()
        left_container.setLayout(left)
        left_container.setFixedWidth(220)

        self.search = QLineEdit(clearButtonEnabled=True)
        self.search.setObjectName("SettingsSearch")
        self.search.setFixedWidth(220)
        self.search.setPlaceholderText("Find a setting")
        self.search.textChanged.connect(self.on_search_text_changed)

        self.list = QListWidget()
        self.list.setObjectName("SettingsSidebar")
        self.list.setFixedWidth(220)
        self.list.setFocusPolicy(Qt.NoFocus)

        left.addWidget(self.search)
        left.addWidget(self.list, 1)   # stretch=1 fills all remaining vertical space

        self.restore_defaults_btn = QPushButton("Restore Defaults")
        self.restore_defaults_btn.setObjectName("RestoreDefaultsBtn")
        self.restore_defaults_btn.setFixedWidth(220)
        self.restore_defaults_btn.setCursor(Qt.PointingHandCursor)
        self.restore_defaults_btn.clicked.connect(self.reset_all_settings)
        left.addWidget(self.restore_defaults_btn)

        # Search dropdown
        self.search_results = QListWidget(self)
        self.search_results.setObjectName("SearchResultsList")
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
        self.build_extra_pages()
        self.list.itemClicked.connect(self.on_sidebar_changed)
        self.list.setCurrentRow(0)

        # Set up Ctrl+F keyboard shortcut to focus search bar
        QShortcut(Qt.CTRL | Qt.Key_F, self).activated.connect(self.focus_search_bar)

    # ----- BUILD -----

    @property
    def root_page_count(self) -> int:
        return len(self.settings) + len(self.extra_pages)

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

    def build_extra_pages(self):
        """Append non-settings sidebar pages (e.g. Vault) after the generated pages."""
        self.extra_page_widgets.clear()
        for label, widget in self.extra_pages:
            self.list.addItem(QListWidgetItem(label))
            self.stack.addWidget(widget)
            self.extra_page_widgets.append(widget)

    def build_search_index(self):
        """ Build the search index for all settings. """
        self.search_index.clear()

        def walk(category, node, path):
            for key, value in node.items():
                new_path = path + [key]

                if isinstance(value, dict) and "value" in value:
                    label = key.replace("_", " ").title()
                    desc = value.get("description", "")
                    text = f"{label} {desc}".lower()

                    self.search_index.append(
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

    def focus_search_bar(self):
        """
        Focus the search bar and select all text.

        Called when Ctrl+F keyboard shortcut is activated.

        Returns:
            None
        """
        self.search.setFocus()
        self.search.selectAll()

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

        matches = [r for r in self.search_index if text in r.text][:15]

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
        self.nav_stack.clear()

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
        self.nav_stack.clear()

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
            self.nav_stack.append(current)

        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

        # Newly created sub-pages do not pass through the dialog-wide refresh
        # done at startup, so apply the same font-role mapping immediately.
        self.refresh_widget_fonts(page)
        if hasattr(page, "refresh_breadcrumb_fonts"):
            page.refresh_breadcrumb_fonts()

    def pop_page(self):
        """ Remove the current page and go back to the previous one. """
        if not self.nav_stack:
            return

        current = self.stack.currentWidget()
        previous = self.nav_stack.pop()

        self.stack.setCurrentWidget(previous)
        self.stack.removeWidget(current)
        current.deleteLater()

    def pop_pages(self, count: int):
        """ Pop multiple pages from the navigation stack. """
        for _ in range(count):
            if not self.nav_stack:
                break
            self.pop_page()

    def reset_navigation(self, select_row=0):
        """ Reset navigation to a specific root page. """
        self.nav_stack.clear()
        self.stack.setCurrentIndex(select_row)
        self.list.setCurrentRow(select_row)

        for i in range(self.stack.count()):
            page = self.stack.widget(i)
            if hasattr(page, "apply_search_highlight"):
                page.apply_search_highlight("")

    def on_sidebar_changed(self, item: QListWidgetItem):
        """ Handle when the user clicks a sidebar item """
        row = self.list.row(item)

        # If user clicked the same root again, reset navigation and return
        if row == self.last_sidebar_row:
            self.reset_navigation(row)
            return

        self.last_sidebar_row = row

        # Clear deep navigation
        self.nav_stack.clear()

        # Remove all stacked sub-pages (keep root pages only)
        root_count = self.root_page_count
        while self.stack.count() > root_count:
            widget = self.stack.widget(self.stack.count() - 1)
            self.stack.removeWidget(widget)
            widget.deleteLater()

        # Navigate to root page
        self.stack.setCurrentIndex(row)

    # ----- SETTINGS -----

    def approve_setting_change(self, path: list[str], old_value, new_value) -> bool:
        """
        Approve a setting change before it is persisted.

        Args:
            path (list[str]): The full path of the setting being changed.
            old_value (Any): The current saved value.
            new_value (Any): The requested new value.

        Returns:
            bool: True when the change should be applied.
        """
        if path != ["general", "clipboard_behavior", "clipboard_timeout"]:
            return True

        if str(new_value).strip().lower() != "off":
            return True

        if str(old_value).strip().lower() == "off":
            return True

        msg = QMessageBox(self)
        msg.setWindowTitle("Disable Clipboard Cleanup")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "Turning clipboard cleanup off can leave expanded snippet content in your clipboard until you replace it."
        )
        msg.setInformativeText("Do you want to keep clipboard cleanup disabled?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        return msg.exec() == QMessageBox.Yes

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

            # Trigger immediate UI refresh for appearance changes.
            # NOTE: settings_dialog.settings and window.parent.settings are the SAME
            # dict reference, so save_settings()'s old != new comparisons are always
            # False (both sides read the already-mutated dict).  We must drive the
            # refresh from here instead.
            if path and path[0] == "appearance":
                try:
                    window = self.parent()
                    if path[1:2] == ["advanced"]:
                        # Font family / sizes / button sizes changed
                        if hasattr(window, 'refresh_font_display'):
                            window.refresh_font_display()
                    else:
                        # Theme, ui_scale, or accent_color changed
                        if hasattr(window, 'refresh_theme_display'):
                            window.refresh_theme_display()
                except Exception:
                    pass

    def reset_all_settings(self):
        """ Reset all settings to their default values after user confirmation. """
        msg = QMessageBox(self)
        msg.setWindowTitle("Restore Defaults")
        msg.setText("Are you sure you want to restore all settings to their default values?")
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        if msg.exec() != QMessageBox.Yes:
            return

        # Walk the settings tree and reset all values to defaults
        self.reset_defaults_recursive(self.settings)

        # Save the reset settings
        if callable(self.save_callback):
            self.save_callback(self.settings)

        # Full refresh: theme + fonts may have changed
        try:
            window = self.parent()
            if hasattr(window, 'refresh_font_display'):
                window.refresh_font_display()
        except Exception:
            pass

        # Rebuild all root pages to reflect the new values
        self.rebuild_pages()
        self.toast.show_toast()

    def reset_defaults_recursive(self, node: dict):
        """ Recursively reset all leaf settings that have a 'default' key. """
        for key, value in node.items():
            if not isinstance(value, dict):
                continue

            if "value" in value and "default" in value:
                value["value"] = value["default"]
            else:
                self.reset_defaults_recursive(value)

    def rebuild_pages(self):
        """ Tear down and rebuild all root category pages. """
        self.nav_stack.clear()

        # Detach extra page widgets before destroying everything
        for widget in self.extra_page_widgets:
            self.stack.removeWidget(widget)
        self.extra_page_widgets.clear()

        # Remove and destroy all remaining (generated) pages
        while self.stack.count() > 0:
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()

        # Rebuild generated pages then re-attach extra pages
        self.build()
        self.build_search_index()
        self.build_extra_pages()

        # Restore sidebar selection
        row = max(0, self.last_sidebar_row)
        if row < self.list.count():
            self.list.setCurrentRow(row)
            self.stack.setCurrentIndex(row)

    def applyStyles(self):
        """Apply fonts from main app to all widgets."""
        try:
            font = self.get_medium_font()
            self.setFont(font)

            if hasattr(self, 'search') and self.search:
                self.search.setFont(font)
            if hasattr(self, 'list') and self.list:
                self.list.setFont(font)
            if hasattr(self, 'restore_defaults_btn') and self.restore_defaults_btn:
                self.restore_defaults_btn.setFont(font)
            if hasattr(self, 'search_results') and self.search_results:
                self.search_results.setFont(font)

            for i in range(self.stack.count()):
                page = self.stack.widget(i)
                self.apply_font_to_widget_tree(page, font)
                if hasattr(page, "refresh_breadcrumb_fonts"):
                    page.refresh_breadcrumb_fonts()
                if hasattr(page, "applyStyles"):
                    page.applyStyles()
        except Exception:
            pass

    def apply_font_to_widget_tree(self, widget, font):
        """Recursively apply font to all widgets in tree, using size variants by role."""
        from PySide6.QtWidgets import (
            QWidget, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton
        )

        try:
            main_app = getattr(self.parent(), 'parent', None)

            def font_for(w):
                if main_app:
                    name = w.objectName()
                    if name == "SettingsHeader":
                        return getattr(main_app, 'large_font_size_bold', getattr(main_app, 'large_font_size', font))
                    if name == "SettingsChevron":
                        return getattr(main_app, 'large_font_size', font)
                    if name == "SettingsCardTitle":
                        return getattr(main_app, 'medium_font_size_bold', font)
                    if name == "SettingsCardDescription":
                        return getattr(main_app, 'small_font_size', font)
                return font

            applicable = (QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton)

            if isinstance(widget, applicable):
                widget.setFont(font_for(widget))
                if isinstance(widget, QComboBox) and widget.lineEdit():
                    widget.lineEdit().setFont(font_for(widget))

            # findChildren with a tuple of types crashes PySide6; use QWidget + isinstance
            for child in widget.findChildren(QWidget):
                if isinstance(child, applicable):
                    child.setFont(font_for(child))
                    if isinstance(child, QComboBox) and child.lineEdit():
                        child.lineEdit().setFont(font_for(child))
        except Exception:
            pass

    def refresh_widget_fonts(self, widget):
        """Recursively update fonts on widget and all children."""
        try:
            self.apply_font_to_widget_tree(widget, self.get_medium_font())
        except Exception:
            pass

    def get_medium_font(self):
        """Return the current medium font from the main app, or a fallback."""
        from PySide6.QtGui import QFont
        app = getattr(self.parent(), 'parent', None)
        if app and hasattr(app, 'medium_font_size'):
            return app.medium_font_size
        return QFont()


