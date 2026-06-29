from pathlib import Path
import re
import logging

from PySide6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QMessageBox, QInputDialog,
    QLineEdit, QHBoxLayout, QComboBox, QPushButton, QSizePolicy
)
from PySide6.QtGui import QStandardItem, QPixmap, QShortcut
from PySide6.QtCore import Qt, Signal, QTimer, QObject, QEvent

from .snippet_table import SnippetTable
from .snippet_form  import SnippetForm
from .home_widget   import HomeWidget

logger = logging.getLogger(__name__)


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
    trigger_reload = Signal()                 # Full refresh (import, bulk ops, folder moves)
    trigger_snippet_saved = Signal(object)    # incremental save - snippet entry dict
    trigger_snippet_deleted = Signal(int)     # incremental delete - snippet id

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

        # Adding safe reload timer to prevent database lock issues
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(50)  # 50ms delay to ensure DB operations complete
        self.reload_timer.timeout.connect(self.perform_reload)

        # Track expand state before search started (None = not in search mode)
        self.pre_search_expanded = None

        self.initUI()
        # Lazy load the snippets; loads as soon as UI is fully rendered
        QTimer.singleShot(0, self.load_snippets)

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
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("Search all the things...")
        self.search_bar.setMinimumWidth(100)
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        # This line must go here to ensure we initalize search first
        self.search_timer.timeout.connect(self.run_search)

        self.filter_dropdown = QComboBox()
        self.filter_dropdown.setObjectName("FilterDropdown")
        self.filter_dropdown.addItem("All Snippets")
        self.filter_dropdown.addItem("Enabled Only")
        self.filter_dropdown.addItem("Disabled Only")
        self.filter_dropdown.setMinimumWidth(100)
        self.filter_dropdown.setMaximumWidth(150)
        self.filter_dropdown.currentIndexChanged.connect(self.run_search)

        arrow = "↓" if not self.main.settings["general"]["table_behavior"]["expand_folders_on_load"].get("value", False) else "↑"
        self.toggle_collapse_button = QPushButton(arrow)
        self.toggle_collapse_button.setObjectName("ToggleCollapseBtn")
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
        self.table.folderSelected.connect(self.on_folder_selected)
        self.table.refreshSignal.connect(self.load_snippets)
        # folder signals
        self.table.addFolder.connect(self.on_add_folder)
        self.table.renameFolder.connect(self.on_rename_folder)
        self.table.deleteFolder.connect(self.on_delete_folder)
        self.table.folderMoved.connect(self.on_folder_moved)
        self.table.snippetMoved.connect(self.on_snippet_moved)
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

        # apply theme and fonts
        self.applyStyles()

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

        # Always pre-load vault folder set so lock icons render correctly.
        # "Vault" is always included so the folder is visible even before setup.
        try:
            vault_folders = list(self.main.snippet_db.get_vault_folders())
            if "Vault" not in vault_folders:
                vault_folders.append("Vault")
            self.table.set_vault_folders(vault_folders)
        except Exception:
            pass

        snippets = self.main.snippet_db.get_all_snippets()
        self.table.load_entries(snippets)
        self.parent.statusBar().showMessage(old_text)

    def safe_reload_snippets(self):
        """
        Schedule a safe reload of snippets with a small delay.

        Uses a QTimer to defer the reload, preventing database lock contention
        when multiple operations happen in quick succession (e.g., drag-drop,
        move, delete). This ensures the database finishes its operation before
        we try to reload.

        Returns:
            None
        """
        self.reload_timer.stop()  # Reset timer if already running
        self.reload_timer.start()  # Will trigger perform_reload after 50ms

    def perform_reload(self):
        """
        Perform the actual reload after the safety delay.

        Called by the reload_timer when it expires after a database operation.

        Returns:
            None
        """
        try:
            self.load_snippets()
            self.trigger_reload.emit()
        except Exception as e:
            logger.error(f"Error during safe reload: {e}")
            self.main.message_box.warning(
                f"Error reloading snippets: {e}",
                title="Reload Error"
            )

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

    def on_folder_selected(self, folder_path: str) -> None:
        """Update the form's folder field when a folder row is clicked.

        Only acts when the snippet form is already visible, so the current
        widget (home or form) is never displaced by a folder click.

        Args:
            folder_path: Full folder path of the clicked folder row.
        """
        if self.stack.currentWidget() is self.form and folder_path:
            self.form.folder_input.setCurrentText(folder_path)

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
            
            # Vault transition confirmation (before writing to DB)
            if not self.check_vault_form_transition(entry):
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

            # Emit before load_snippets so on_snippet_saved_vault clears is_encrypted
            # before the table refresh can reload the snippet with a stale flag.
            self.trigger_snippet_saved.emit(entry)
            self.load_snippets()    # Reload snippets to reflect changes
            self.table.select_entry(entry)
            self.form.invalidate_caches()  # Tags may have changed

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

        new_folder = name.strip()
        # If triggered from a folder context menu, make the new folder a sub-folder
        if parent_item is not None:
            folder_data = parent_item.data(Qt.UserRole)
            if isinstance(folder_data, dict) and folder_data.get("_type") == "folder":
                new_folder = folder_data["path"] + "/" + new_folder

        self.show_new_form()
        self.form.folder_input.setCurrentText(new_folder)
        
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
        folder_data = folder_item.data(Qt.UserRole) if folder_item is not None else None
        old = (
            folder_data["path"]
            if isinstance(folder_data, dict) and "path" in folder_data
            else folder_item.text()
        )
        # Display only the last segment in the prompt; keep the rest of the path
        last_segment = old.split("/")[-1]
        new_last, ok = QInputDialog.getText(
            self, 'Rename Folder', f'New name for "{old}":', text=last_segment
        )
        if not ok or not new_last.strip():
            return
        parts = old.split("/")
        parts[-1] = new_last.strip()
        new = "/".join(parts)
        if new == old:
            return
        db = self.main.snippet_db
        db.rename_folder(old, new)
        # Keep vault_folders in sync when the renamed folder is a vault root.
        if db.is_vault_folder(old):
            db.remove_vault_folder(old)
            db.add_vault_folder(new)
        self.load_snippets()
        self.form.invalidate_caches()  # Folder list has changed
        self.main.message_box.info(f'Renamed folder "{old}" to "{new}"', title='Folder Renamed')

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
            folder_data = parent_item.data(Qt.UserRole)
            if isinstance(folder_data, dict) and folder_data.get("_type") == "folder":
                self.form.folder_input.setCurrentText(folder_data["path"])
            else:
                self.form.folder_input.setCurrentText(parent_item.text())

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
        folder_data = folder_item.data(Qt.UserRole) if folder_item is not None else None
        name = (
            folder_data["path"]
            if isinstance(folder_data, dict) and "path" in folder_data
            else folder_item.text()
        )
        confirm = self.main.message_box.question(
            f'Delete folder "{name}" and all its snippets (including sub-folders)?',
            title="Delete Folder",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return
        
        self.main.snippet_db.delete_folder(name)
        self.load_snippets()
        self.form.invalidate_caches()  # Folder list has changed

    def on_folder_moved(self, old_path: str, new_path: str):
        """Persist a folder drag-and-drop move, handling vault encrypt/decrypt transitions.

        Detects when the move crosses a vault boundary and:
        - Shows a confirmation dialog before encrypting or decrypting.
        - Encrypts all snippets in the subtree when moving into a vault folder.
        - Decrypts all snippets in the subtree when moving out of a vault folder.
        - Updates the ``vault_folders`` registry when a vault root folder itself is moved.

        Args:
            old_path (str): Previous full path, e.g. ``"work"``.
            new_path (str): New full path, e.g. ``"Vault/work"``.

        Returns:
            None
        """
        from PySide6.QtWidgets import QMessageBox
        from utils.vault_manager import VaultError

        db = self.main.snippet_db
        window = self.parent
        vm = window.vault_manager() if hasattr(window, "vault_manager") else None

        old_in_vault = db.is_under_vault_folder(old_path)
        new_in_vault = db.is_under_vault_folder(new_path)
        old_is_vault_root = db.is_vault_folder(old_path)

        cfg = window.vault_config() if hasattr(window, "vault_config") else {}
        is_vault_setup = vm.is_setup(cfg) if vm else False
        if not is_vault_setup:
            table_vault_set = getattr(self.table, "vault_folder_set", set())
            parts = new_path.split("/")
            if any("/".join(parts[:i + 1]) in table_vault_set for i in range(len(parts))):
                msg = QMessageBox(self)
                msg.setWindowTitle("Vault Not Configured")
                msg.setText(
                    "Cannot move folder into vault.\n\nThe vault is not set up."
                )
                msg.setMinimumWidth(250)
                setup_btn = msg.addButton("Set Up Vault", QMessageBox.AcceptRole)
                msg.addButton("Cancel", QMessageBox.RejectRole)
                msg.setDefaultButton(setup_btn)
                msg.exec()
                if msg.clickedButton() == setup_btn:
                    window.show_vault_settings()
                return

        moving_into_vault = (not old_in_vault) and new_in_vault
        moving_out_of_vault = old_in_vault and (not new_in_vault) and (not old_is_vault_root)

        if moving_into_vault or moving_out_of_vault:
            snippets = db.get_snippets_by_folder(old_path)
            count = len(snippets)
            noun = "snippet" if count == 1 else "snippets"

            if moving_into_vault:
                if vm and not vm.is_unlocked():
                    self.main.message_box.warning(
                        "The vault is locked. Unlock the vault before moving a folder into it.",
                        title="Vault Locked",
                    )
                    return
                answer = QMessageBox.question(
                    self,
                    "Move Folder Into Vault",
                    f'Moving "{old_path}" into a vault folder will encrypt '
                    f'{count} {noun} (including any sub-folders).\n\nDo you wish to proceed?',
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
            else:
                if vm and not vm.is_unlocked():
                    self.main.message_box.warning(
                        "The vault is locked. Unlock the vault before moving an encrypted "
                        "folder out of it.",
                        title="Vault Locked",
                    )
                    return
                answer = QMessageBox.question(
                    self,
                    "Move Folder Out of Vault",
                    f'Moving "{old_path}" out of the vault will permanently decrypt '
                    f'{count} {noun} (including any sub-folders).\n\nDo you wish to proceed?',
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )

            if answer != QMessageBox.Yes:
                return

        try:
            db.rename_folder(old_path, new_path)

            # Keep vault_folders in sync when a vault root itself is moved.
            if old_is_vault_root:
                db.remove_vault_folder(old_path)
                # Only re-register as a root if the new location is not already
                # inside another vault (it would be implicitly protected).
                if not db.is_under_vault_folder(new_path):
                    db.add_vault_folder(new_path)

            # Encrypt or decrypt all snippets now living under new_path.
            if (moving_into_vault or moving_out_of_vault) and vm:
                snippets = db.get_snippets_by_folder(new_path)
                updates = []
                for s in snippets:
                    sid = s["id"]
                    content = s.get("snippet", "")
                    is_enc = bool(s.get("is_encrypted"))
                    if moving_into_vault and not is_enc:
                        updates.append((sid, vm.encrypt(content), True))
                    elif moving_out_of_vault and is_enc:
                        updates.append((sid, vm.decrypt(content), False))
                db.bulk_encrypt_folder_snippets(updates)

            self.load_snippets()
            self.trigger_reload.emit()
        except VaultError as exc:
            logger.warning("Vault error during folder move: %s", exc)
            self.main.message_box.warning(str(exc), title="Vault Locked")
        except Exception as exc:
            logger.error("Error moving folder: %s", exc)
            self.main.message_box.warning(
                f"Error moving folder: {exc}",
                title="Move Error",
            )

    def check_vault_form_transition(self, entry: dict) -> bool:
        """Show confirmation or error dialogs for vault ↔ non-vault folder changes.

        Must be called before ``insert_snippet`` so the user can cancel without
        any DB write occurring.

        Args:
            entry (dict): The entry dict from ``get_entry()``, with the
                *destination* folder already set.

        Returns:
            bool: True if the save should proceed, False to cancel.
        """
        from PySide6.QtWidgets import QMessageBox

        db = self.main.snippet_db
        window = self.parent
        vm = window.vault_manager() if hasattr(window, "vault_manager") else None

        snippet_id = entry.get("id")
        dest_is_vault = db.is_under_vault_folder(entry.get("folder", ""))

        src_is_encrypted = False
        src_is_vault = False
        if snippet_id:
            db_entry = db.get_snippet(snippet_id) or {}
            src_is_encrypted = bool(db_entry.get("is_encrypted"))
            src_is_vault = db.is_under_vault_folder(db_entry.get("folder", ""))

        moving_into_vault = (not src_is_vault) and dest_is_vault
        moving_out_of_vault = src_is_encrypted and (not dest_is_vault)

        if moving_into_vault:
            if vm and not vm.is_unlocked():
                self.main.message_box.warning(
                    "The vault is locked. Unlock the vault before saving a snippet "
                    "to a vault folder.",
                    title="Vault Locked",
                )
                return False
            answer = QMessageBox.question(
                self,
                "Move Into Vault",
                "This snippet is about to be moved to the vault and encrypted.\n\n"
                "Do you wish to proceed?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            return answer == QMessageBox.Yes

        if moving_out_of_vault:
            if vm and not vm.is_unlocked():
                self.main.message_box.warning(
                    "The vault is locked. Unlock the vault before moving an encrypted "
                    "snippet out of it.",
                    title="Vault Locked",
                )
                return False
            answer = QMessageBox.question(
                self,
                "Move Out of Vault",
                "This snippet will be permanently decrypted and moved out of the vault.\n\n"
                "Do you wish to proceed?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            return answer == QMessageBox.Yes

        return True

    def on_snippet_moved(self, entry: dict, new_folder: str):
        """Persist a snippet drag-and-drop move, handling vault encrypt/decrypt transitions.

        When moving a snippet out of a vault folder the user is shown a
        confirmation dialog because the content will be permanently decrypted.
        When moving into a vault folder the vault must be unlocked.  All
        encrypt/decrypt work is delegated to
        :meth:`SnippetDB.insert_snippet_vault_aware` so the invariant is
        enforced at the data layer.

        Args:
            entry (dict): Original snippet entry dict (folder = *source* folder).
            new_folder (str): Destination folder path.

        Returns:
            None
        """
        from utils.vault_manager import VaultError

        db = self.main.snippet_db
        window = self.parent  # QSnippet main window (stored directly, not callable)
        vm = window.vault_manager() if hasattr(window, "vault_manager") else None

        src_encrypted = bool(entry.get("is_encrypted"))
        dest_is_vault = db.is_vault_folder(new_folder)
        src_is_vault = db.is_vault_folder(entry.get("folder", ""))

        from PySide6.QtWidgets import QMessageBox

        cfg = window.vault_config() if hasattr(window, "vault_config") else {}
        is_vault_setup = vm.is_setup(cfg) if vm else False
        if not is_vault_setup:
            table_vault_set = getattr(self.table, "vault_folder_set", set())
            parts = new_folder.split("/")
            if any("/".join(parts[:i + 1]) in table_vault_set for i in range(len(parts))):
                msg = QMessageBox(self)
                msg.setWindowTitle("Vault Not Configured")
                msg.setText(
                    "Cannot move snippet into vault.\n\nThe vault is not set up."
                )
                msg.setMinimumWidth(250)
                setup_btn = msg.addButton("Set Up Vault", QMessageBox.AcceptRole)
                msg.addButton("Cancel", QMessageBox.RejectRole)
                msg.setDefaultButton(setup_btn)
                msg.exec()
                if msg.clickedButton() == setup_btn:
                    window.show_vault_settings()
                return

        # Confirm before encrypting into vault
        if not src_is_vault and dest_is_vault:
            answer = QMessageBox.question(
                self,
                "Move Into Vault",
                "This snippet is about to be moved to the vault and encrypted.\n\n"
                "Do you wish to proceed?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        # Confirm before permanently decrypting
        if src_encrypted and not dest_is_vault:
            answer = QMessageBox.question(
                self,
                "Move Out of Vault",
                "This snippet is encrypted. Moving it out of the vault will "
                "permanently decrypt its contents.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            updated = {**entry, "folder": new_folder}
            db.insert_snippet_vault_aware(updated, vault_manager=vm)
            self.load_snippets()
            self.trigger_reload.emit()
        except VaultError as exc:
            logger.warning("Vault error during snippet move: %s", exc)
            self.main.message_box.warning(
                str(exc),
                title="Vault Locked",
            )
        except Exception as exc:
            logger.error("Error moving snippet: %s", exc)
            self.main.message_box.warning(
                f"Error moving snippet: {exc}",
                title="Move Error",
            )

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
        self.trigger_snippet_deleted.emit(entry['id'])  # Incremental expander update
        self.form.invalidate_caches()  # Tags may have changed
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
        updates the table with results, temporarily expands folders when searching
        (if enabled), and optionally triggers an easter egg dialog.

        Returns:
            None
        """
        keyword = self.search_bar.text().strip()
        filter_mode = self.filter_dropdown.currentText()
        is_searching = bool(keyword)

        # Check setting for expand on search behavior
        expand_on_search = self.main.settings["general"]["table_behavior"]["expand_on_search"].get("value", True)

        # On transition into search mode: save current expand state
        if is_searching and self.pre_search_expanded is None:
            self.pre_search_expanded = self.toggle_collapse_button.text() == "↑"

        # On transition out of search mode: capture restore target and reset state
        restore_expanded = None
        if not is_searching and self.pre_search_expanded is not None:
            restore_expanded = self.pre_search_expanded
            self.pre_search_expanded = None

        # Get results from DB
        results = self.main.snippet_db.search_snippets(keyword)

        # Filter further if enabled/disabled only is selected
        if filter_mode == "Enabled Only":
            results = [s for s in results if s.get("enabled", True)]
        elif filter_mode == "Disabled Only":
            results = [s for s in results if not s.get("enabled", False)]

        self.table.load_entries(results)

        # Override expansion state based on search mode
        if expand_on_search:
            if is_searching:
                self.table.expandAll()
                self.toggle_collapse_button.setText("↑")
            elif restore_expanded is not None:
                if restore_expanded:
                    self.table.expandAll()
                    self.toggle_collapse_button.setText("↑")
                else:
                    self.table.collapseAll()
                    self.toggle_collapse_button.setText("↓")

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
        Apply font and size styling to search controls and all child widgets.

        Returns:
            None
        """
        self.search_bar.setFont(self.main.medium_font_size)
        self.filter_dropdown.setFont(self.main.medium_font_size)
        
        self.home_widget.applyStyles()
        self.form.applyStyles()
        self.table.applyStyles()
        self.update()

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

