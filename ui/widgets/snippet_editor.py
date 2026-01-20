from pathlib import Path
import re

from PySide6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QMessageBox, QInputDialog,
    QLineEdit, QHBoxLayout, QComboBox, QPushButton, QSizePolicy
)
from PySide6.QtGui import QStandardItem, QPixmap
from PySide6.QtCore import Qt, Signal, QTimer, QItemSelectionModel

from .snippet_table import SnippetTable
from .snippet_form  import SnippetForm
from .home_widget   import HomeWidget


class SnippetEditor(QWidget):
    trigger_reload = Signal()

    def __init__(self, config_path, main, parent=None):
        super().__init__()
        self.config_path = Path(config_path)
        self.main = main
        self.parent = parent

        # Adding search debounce timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(100)  # 0.1 seconds

        self.initUI()
        self.load_snippets()

    def initUI(self):
        self.splitter = QSplitter(Qt.Horizontal, self)

        self.left_layout = QVBoxLayout()

        # Search bar and filters
        self.search_bar = QLineEdit(clearButtonEnabled=True)
        self.search_bar.setPlaceholderText("Search all the things...")
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        # This line must go here to ensure we initalize search first
        self.search_timer.timeout.connect(self.run_search)

        self.filter_dropdown = QComboBox()
        self.filter_dropdown.addItem("All Snippets")
        self.filter_dropdown.addItem("Enabled Only")
        self.filter_dropdown.addItem("Disabled Only")
        self.filter_dropdown.currentIndexChanged.connect(self.run_search)

        arrow = "↓" if not self.main.settings["general"]["startup_behavior"]["expand_folders_on_load"].get("value", False) else "↑"
        self.toggle_collapse_button = QPushButton(arrow)
        self.toggle_collapse_button.setToolTip("Expand/Collapse All Folders")
        self.toggle_collapse_button.setFixedSize(30, 40)
        self.toggle_collapse_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.toggle_collapse_button.clicked.connect(self.toggle_collapse_folders)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.filter_dropdown)
        search_layout.addWidget(self.toggle_collapse_button)

        # Left: snippet table
        self.table = SnippetTable(main=self.main, parent=self)
        self.table.entrySelected.connect(self.on_entry_selected)
        self.table.refreshSignal.connect(self.load_snippets)
        # folder signals
        self.table.addFolder.connect(self.on_add_folder)
        self.table.renameFolder.connect(self.on_rename_folder)
        self.table.deleteFolder.connect(self.on_delete_folder)
        # snippet signals
        self.table.addSnippet.connect(self.on_add_snippet)
        self.table.editSnippet.connect(self.on_edit_snippet)
        self.table.renameSnippet.connect(self.on_rename_snippet)
        self.table.deleteSnippet.connect(self.on_delete_snippet)

        # Right: stack of home + form
        self.home_widget = HomeWidget(main=self.main, parent=self)
        self.home_widget.new_snippet.connect(self.show_new_form)

        self.form = SnippetForm(main=self.main, parent=self)
        self.form.newClicked.connect(self.show_new_form)
        self.form.saveClicked.connect(self.on_save)
        self.form.deleteClicked.connect(self.on_delete)
        self.form.cancelPressed.connect(self.show_home_widget)

        # Layout
        self.left_layout.addLayout(search_layout)
        self.left_layout.addWidget(self.table)
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.home_widget)
        self.stack.addWidget(self.form)
        self.stack.setCurrentWidget(self.home_widget)

        self.splitter.addWidget(self.left_widget)
        self.splitter.addWidget(self.stack)

        # layout just needs to host the splitter
        vlay = QVBoxLayout()
        vlay.addWidget(self.splitter)
        self.setLayout(vlay)

        # apply theme
        self.update_stylesheet()
    
    def load_snippets(self):
        old_text = self.parent.statusBar().currentMessage() or ""
        self.parent.statusBar().showMessage(f"Loading Snippets...")
        snippets = self.main.snippet_db.get_all_snippets()
        self.table.load_entries(snippets)
        self.parent.statusBar().showMessage(old_text)

    def on_entry_selected(self, entry):
        if entry:
            self.form.clear_form()
            self.stack.setCurrentWidget(self.form)
            self.form.load_entry(entry)
        else:
            self.stack.setCurrentWidget(self.home_widget)    

    def show_home_widget(self, *_):
        """ Show the home widget. """
        self.parent.resume_service() # resume snippet service
        # Should deselect any selected items in tree view
        self.stack.setCurrentWidget(self.home_widget)

    def show_new_form(self, *_):
        self.pause_service()  # Pause snippet service

        # Clear the table selection and form inputs, then swap in form
        # self.table.clear_selection()
        self.form.clear_form()
        self.form.enabled_switch.setChecked(True)   # Set switch to enabled on every new snippet
        self.stack.setCurrentWidget(self.form)

    def toggle_collapse_folders(self):
        """ Toggle between expanding and collapsing all folders in the table. """
        if self.table.isAnyFolderExpanded():
            self.table.collapseAll()
            self.toggle_collapse_button.setText("↓")
        else:
            self.table.expandAll()
            self.toggle_collapse_button.setText("↑")

    # ----- Handlers -----
    def on_save(self, *_):
        try:
            if not self.form.validate():
                return
            
            entry = self.form.get_entry()

            # Detect circular reference
            all_snips = self.main.snippet_db.get_all_snippets()
            if self.detect_circular_reference(entry, all_snips):
                self.main.message_box.error(
                    f'Snippet "{entry["label"]}" references itself or forms a circular chain.',
                    title="Invalid Snippet"
                )
                return
            
            # Insert the snippet into the DB
            # returns True if new, False if updated
            is_new = self.main.snippet_db.insert_snippet(entry)

            if is_new:
                self.main.message_box.info(
                    f'New snippet "{entry["label"]}" created successfully!',
                    title="Snippet Created"
                )
            else:
                self.main.message_box.info(
                    f'Snippet "{entry["label"]}" updated successfully!',
                    title="Snippet Updated"
                )

            self.load_snippets()    # Reload snippets to reflect changes
            self.table.select_entry(entry)
            self.trigger_reload.emit()  # Flag

            # Here we could go home or stay on new form
            # Should make this a setting, for now go home
            if self.main.settings["saving"]["navigate_home_after_save"]["value"]:
                # Navigate home
                self.navigate_home()
            else:
                # Show new form
                self.show_new_form()

        except Exception as e:
            self.main.message_box.error(f'Snippet Save Failed: {e}', title="Save Failed")

    def on_delete(self, *_):
        entry = self.table.current_entry()
        
        if not entry:
            self.showStatus("Could not delete entry!")
            return
        self.on_delete_snippet(entry)
        
    # ----- Helper for on_save -----
    def detect_circular_reference(self, entry, all_snippets) -> bool:
        """Return True if entry would introduce a circular reference."""
        trigger = entry["trigger"]
        visited = set()

        def dfs(current_trigger):
            if current_trigger in visited:
                return True
            visited.add(current_trigger)
            snippet = next((s for s in all_snippets if s["trigger"] == current_trigger), None)
            if not snippet:
                return False
            matches = re.findall(r"\{/(.+?)\}", snippet["snippet"])
            for ref in matches:
                if ref == trigger or dfs(ref):
                    return True
            return False

        return dfs(trigger)

    # ----- Context Menu Actions -----
    def on_add_folder(self, parent_item=None, *_):
        name, ok = QInputDialog.getText(self, 'New Folder', 'Folder name:')
        if not ok or not name.strip():
            return
        self.show_new_form()
        self.form.folder_input.setCurrentText(name.strip())
        
    def on_rename_folder(self, folder_item=None, *_):
        old = folder_item.text()
        new, ok = QInputDialog.getText(self, 'Rename Folder', f'New name for "{old}":', text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        self.main.snippet_db.rename_folder(old, new.strip())
        self.load_snippets()
        self.main.message_box.info(f'Renamed folder "{old}" to "{new.strip()}"', title='Folder Renamed')

    def on_add_snippet(self, parent_item=None, *_):
        self.show_new_form()
        if isinstance(parent_item, QStandardItem):
            itemText = str(parent_item.text())
            self.form.folder_input.setCurrentText(itemText)

    def on_delete_folder(self, folder_item=None, *_):
        name = folder_item.text()
        confirm = self.main.message_box.question(
            f'Delete folder "{name}" and all its snippets?',
            title="Delete Folder",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return
        
        self.main.snippet_db.delete_folder(name)
        self.load_snippets()

    def on_edit_snippet(self, entry=None, *_):
        self.on_entry_selected(entry)

    def on_rename_snippet(self, entry=None, *_):
        old_label = entry.get('label', '')
        new_label, ok = QInputDialog.getText(
            self, 'Rename Snippet', 'New label:', text=old_label
        )

        if not ok or not new_label.strip() or new_label == old_label:
            return
        
        # Need to rename based on ID
        self.main.snippet_db.rename_snippet(entry['id'], new_label.strip())
        self.load_snippets()
        self.main.message_box.info(f'Renamed snippet "{old_label}" to "{new_label.strip()}"', title='Snippet Renamed')
    
    def on_delete_snippet(self, entry):
        confirm = self.main.message_box.question(
            f'Delete snippet "{entry.get("label","")}"?',
            title="Delete Snippet",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return

        # Need to delete by ID
        self.main.snippet_db.delete_snippet(entry['id'])
        self.load_snippets()
        self.navigate_home()

    def handle_rename_action(self):
        """
        Check what is selected in the table and 
        determine if we need to remane folder or snippet.
        """
        sm = self.table.selectionModel()
        if not sm or not sm.hasSelection():
            return

        # Get a row selection in column 0 from the proxy model
        rows = sm.selectedRows(0)
        if not rows:
            # Fallback: sometimes Qt gives only selectedIndexes, grab any and force col 0
            idxs = sm.selectedIndexes()
            if not idxs:
                return
            proxy_idx = idxs[0].sibling(idxs[0].row(), 0)
        else:
            proxy_idx = rows[0]

        if not proxy_idx.isValid():
            return

        # Make sure the view has a current index so current_entry() works
        # This fixes the F2 menu focus issue
        self.table.setCurrentIndex(proxy_idx)

        # First try snippet rename using your existing helper
        entry = self.table.current_entry()
        if entry:
            self.on_rename_snippet(entry)
            return

        # Otherwise treat it as folder
        # Map proxy index to source index using the table’s proxy instance
        src_idx = self.table.proxy.mapToSource(proxy_idx)
        if not src_idx.isValid():
            return

        folder_item = self.table.model.itemFromIndex(src_idx)
        if folder_item is None:
            return

        self.on_rename_folder(folder_item)

    # ----- Search -----
    def on_search_text_changed(self):
        self.search_timer.start()  # restart timer on every keystroke

    def run_search(self):
        keyword = self.search_bar.text().strip()
        filter_mode = self.filter_dropdown.currentText()

        # Get results from DB
        results = self.main.snippet_db.search_snippets(keyword)

        # Filter further if enabled/disabled only is selected
        if filter_mode == "Enabled Only":
            results = [s for s in results if s.get("enabled", True)]
        elif filter_mode == "Disabled Only":
            results = [s for s in results if not s.get("enabled", False)]

        self.table.load_entries(results)

        # Easter Egg
        # If user types "cat" in search, show cat dialog
        if (
            keyword.lower() == "cat" and 
            self.main.settings["general"]["extra_features"]["easter_eggs_enabled"].get("value", True)
            ):
            self.search_bar.clear()
            self.show_cat_dialog()
            return
        
    def show_cat_dialog(self):
        box = QMessageBox(self)
        box.setWindowTitle("Meow!")
        box.setText(
            "Enjoy this picutre of my cat :)\n\n" \
            "You can turn off easter eggs in the settings.\n\n"
        )

        pixmap = QPixmap(self.main.images["cat"])
        box.setIconPixmap(pixmap.scaledToWidth(256, Qt.SmoothTransformation))

        box.exec()

    def applyStyles(self):
        """Fucntion to call when you need toupdate the UI. """
        self.home_widget.applyStyles()
        self.form.applyStyles()
        self.update()
        self.main.app.processEvents()

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        self.setStyleSheet(""" 
            QPushButton {
                padding: 8px;
            } 

            QComboBox {
                padding: 8px;
            }

            QLineEdit {
                padding: 8px;
            }
        """)

    def showStatus(self, msg=""):
        original_msg = self.parent.statusBar().currentMessage() or ""
        self.parent.statusBar().showMessage(msg)
        QTimer.singleShot(5000, lambda: self.parent.statusBar().showMessage(original_msg))

    def navigate_home(self):
        self.resume_service()
        self.stack.setCurrentIndex(0)   # go home

    def pause_service(self):
        self.parent.statusBar().showMessage(f"Service status: Paused")
        self.parent.snippet_service.pause()

    def resume_service(self):
        self.parent.statusBar().showMessage(f"Service status: Running")
        self.parent.snippet_service.resume()