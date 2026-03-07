from pathlib import Path
import re

from PySide6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QMessageBox, QInputDialog,
    QLineEdit, QHBoxLayout, QComboBox, QPushButton, QSizePolicy
)
from PySide6.QtGui import QStandardItem, QPixmap, QShortcut
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent

from .snippet_table import SnippetTable
from .snippet_form  import SnippetForm
from .home_widget   import HomeWidget


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


class WidgetMouseFilter(QObject):
    """
    Event filter to handle mouse clicks on the widget.
    
    Removes focus from the search bar when clicking on empty space or labels.
    """
    def __init__(self, search_bar):
        super().__init__()
        self.search_bar = search_bar
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            # Defocus search bar by clearing focus
            self.search_bar.clearFocus()
        return super().eventFilter(obj, event)


class SnippetEditor(QWidget):
    trigger_reload = Signal()

    def __init__(self, config_path, main, parent=None):
        """
        Initialize the SnippetEditor widget.

        Sets up configuration paths, references to the main application,
        initializes the search debounce timer, and loads snippets into the table.

        Args:
            config_path (Any): Path to the configuration file.
            main (Any): Reference to the main application object.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
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
        """
        Initialize and configure the user interface components.

        Creates layouts, search controls, snippet table, form stack,
        connects signals, and applies the initial stylesheet.

        Returns:
            None
        """
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

        # Set up Ctrl+F keyboard shortcut to focus search bar
        QShortcut(Qt.CTRL | Qt.Key_F, self).activated.connect(self.focus_search_bar)
    
    def focus_search_bar(self):
        """
        Focus the search bar and select all text.

        Called when Ctrl+F keyboard shortcut is activated.

        Returns:
            None
        """
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    def load_snippets(self):
        """
        Load all snippets from the database into the table.

        Temporarily updates the status bar while loading and restores
        the previous message afterward.

        Returns:
            None
        """
        old_text = self.parent.statusBar().currentMessage() or ""
        self.parent.statusBar().showMessage(f"Loading Snippets...")
        snippets = self.main.snippet_db.get_all_snippets()
        self.table.load_entries(snippets)
        self.parent.statusBar().showMessage(old_text)

    def on_entry_selected(self, entry):
        """
        Handle selection of a snippet entry in the table.

        Displays the snippet form populated with the selected entry,
        or shows the home widget if no entry is selected.

        Args:
            entry (dict): The selected snippet entry.

        Returns:
            None
        """
        if entry:
            self.form.clear_form()
            self.stack.setCurrentWidget(self.form)
            self.form.load_entry(entry)
        else:
            self.stack.setCurrentWidget(self.home_widget)    

    def show_home_widget(self, *_):
        """
        Display the home widget.

        Resumes the snippet service and switches the stacked widget
        to the home view.

        Returns:
            None
        """
        self.parent.resume_service() # resume snippet service
        # Should deselect any selected items in tree view
        self.stack.setCurrentWidget(self.home_widget)

    def show_new_form(self, *_):
        """
        Display the form for creating a new snippet.

        Pauses the snippet service, clears existing form data,
        enables the snippet by default, and switches to the form view.

        Returns:
            None
        """
        self.pause_service()  # Pause snippet service

        # Clear the table selection and form inputs, then swap in form
        # self.table.clear_selection()
        self.form.clear_form()
        self.form.enabled_switch.setChecked(True)   # Set switch to enabled on every new snippet
        self.stack.setCurrentWidget(self.form)

    def toggle_collapse_folders(self):
        """
        Toggle expansion state of all folders in the snippet table.

        Collapses all folders if any are expanded, otherwise expands all,
        and updates the toggle button indicator.

        Returns:
            None
        """
        if self.table.isAnyFolderExpanded():
            self.table.collapseAll()
            self.toggle_collapse_button.setText("↓")
        else:
            self.table.expandAll()
            self.toggle_collapse_button.setText("↑")

    # ----- Handlers -----
    def on_save(self, *_):
        """
        Handle saving of a snippet.

        Validates form input, checks for circular references,
        inserts or updates the snippet in the database, reloads
        the table, and optionally navigates home.

        Returns:
            None

        Raises:
            Exception: If an unexpected error occurs during save.
        """
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
        """
        Handle deletion of the currently selected snippet.

        Retrieves the selected entry and delegates deletion
        to the snippet deletion handler.

        Returns:
            None
        """
        entry = self.table.current_entry()
        
        if not entry:
            self.showStatus("Could not delete entry!")
            return
        self.on_delete_snippet(entry)
        
    # ----- Helper for on_save -----
    def detect_circular_reference(self, entry, all_snippets) -> bool:
        """
        Determine whether a snippet introduces a circular reference.

        Performs a depth-first search through referenced snippets
        to detect cycles based on trigger values.

        Args:
            entry (dict): The snippet entry being evaluated.
            all_snippets (list[dict]): All existing snippets.

        Returns:
            bool: True if a circular reference is detected, otherwise False.
        """
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
        """
        Handle creation of a new folder.

        Prompts the user for a folder name and prepares the form
        with the specified folder selected.

        Args:
            parent_item (Any): Optional parent item reference.

        Returns:
            None
        """
        name, ok = QInputDialog.getText(self, 'New Folder', 'Folder name:')
        if not ok or not name.strip():
            return
        self.show_new_form()
        self.form.folder_input.setCurrentText(name.strip())
        
    def on_rename_folder(self, folder_item=None, *_):
        """
        Handle renaming of an existing folder.

        Prompts the user for a new folder name, updates the database,
        reloads snippets, and displays a confirmation message.

        Args:
            folder_item (Any): The folder item to rename.

        Returns:
            None
        """
        old = folder_item.text()
        new, ok = QInputDialog.getText(self, 'Rename Folder', f'New name for "{old}":', text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        self.main.snippet_db.rename_folder(old, new.strip())
        self.load_snippets()
        self.main.message_box.info(f'Renamed folder "{old}" to "{new.strip()}"', title='Folder Renamed')

    def on_add_snippet(self, parent_item=None, *_):
        """
        Handle creation of a new snippet within a folder.

        Displays the new snippet form and preselects the folder
        if a parent item is provided.

        Args:
            parent_item (Any): Optional parent item reference.

        Returns:
            None
        """
        self.show_new_form()
        if isinstance(parent_item, QStandardItem):
            itemText = str(parent_item.text())
            self.form.folder_input.setCurrentText(itemText)

    def on_delete_folder(self, folder_item=None, *_):
        """
        Handle deletion of a folder and its snippets.

        Prompts the user for confirmation before removing the folder
        from the database and reloading snippets.

        Args:
            folder_item (Any): The folder item to delete.

        Returns:
            None
        """
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
        """
        Handle editing of a snippet entry.

        Delegates to the entry selection handler to load the snippet
        into the form.

        Args:
            entry (dict): The snippet entry to edit.

        Returns:
            None
        """
        self.on_entry_selected(entry)

    def on_rename_snippet(self, entry=None, *_):
        """
        Handle renaming of a snippet.

        Prompts the user for a new label, updates the database,
        reloads snippets, and displays a confirmation message.

        Args:
            entry (dict): The snippet entry to rename.

        Returns:
            None
        """
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
        """
        Handle deletion of a snippet.

        Prompts the user for confirmation, deletes the snippet
        from the database, reloads snippets, and navigates home.

        Args:
            entry (dict): The snippet entry to delete.

        Returns:
            None
        """
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
        Handle rename action based on current table selection.

        Determines whether the selected item is a snippet or folder
        and invokes the appropriate rename handler.

        Returns:
            None
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
        """
        Handle changes in the search bar text.

        Restarts the debounce timer to delay execution of the search.

        Returns:
            None
        """
        self.search_timer.start()  # restart timer on every keystroke

    def run_search(self):
        """
        Execute the snippet search operation.

        Filters snippets based on keyword and enabled/disabled status,
        updates the table with results, and optionally triggers an
        easter egg dialog.

        Returns:
            None
        """
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
        """
        Display a dialog containing a cat image.

        Shows an informational message box with an embedded image
        and optional settings note.

        Returns:
            None
        """
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
        """
        Apply updated styles to child widgets and refresh the UI.

        Calls style update methods on contained widgets and processes
        pending application events.

        Returns:
            None
        """
        self.home_widget.applyStyles()
        self.form.applyStyles()
        self.update()
        self.main.app.processEvents()

    def update_stylesheet(self):
        """
        Update the widget stylesheet.

        Applies styling rules for buttons, combo boxes, and line edits.

        Returns:
            None
        """
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
        """
        Display a temporary status message.

        Shows the provided message in the status bar and restores
        the previous message after a delay.

        Args:
            msg (str): Message to display.

        Returns:
            None
        """
        original_msg = self.parent.statusBar().currentMessage() or ""
        self.parent.statusBar().showMessage(msg)
        QTimer.singleShot(5000, lambda: self.parent.statusBar().showMessage(original_msg))

    def navigate_home(self):
        """
        Navigate to the home view.

        Resumes the snippet service and switches the stacked widget
        to the home index.

        Returns:
            None
        """
        self.resume_service()
        self.stack.setCurrentIndex(0)   # go home

    def pause_service(self):
        """
        Pause the snippet service.

        Updates the status bar and pauses the background snippet service.

        Returns:
            None
        """
        self.parent.statusBar().showMessage(f"Service status: Paused")
        self.parent.snippet_service.pause()

    def resume_service(self):
        """
        Resume the snippet service.

        Updates the status bar and resumes the background snippet service.

        Returns:
            None
        """
        self.parent.statusBar().showMessage(f"Service status: Running")
        self.parent.snippet_service.resume()
