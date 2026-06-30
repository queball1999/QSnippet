
import logging
from PySide6.QtWidgets import (
    QTreeView, QAbstractItemView, QHeaderView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont
from PySide6.QtCore import (
    Qt, Signal, QModelIndex, QSortFilterProxyModel
)

# Import context menus
from ui.menus import (
    SnippetContextMenu,
    FolderContextMenu,
    EmptyContextMenu
)

logger = logging.getLogger(__name__)

class SnippetTable(QTreeView):
    # Signals for context‐menu actions
    addFolder = Signal(object)          # parent folder (QStandardItem) or None
    addSnippet = Signal(object)         # parent folder (QStandardItem)
    editSnippet = Signal(dict)           # entry data
    renameFolder = Signal(QStandardItem)  # folder item
    renameSnippet = Signal(dict)           # entry data
    deleteFolder = Signal(QStandardItem)  # folder item
    deleteSnippet = Signal(dict)           # entry data
    entrySelected = Signal(object)         # when a snippet is clicked (dict or None)
    folderSelected = Signal(str)           # when a folder row is clicked (folder path)
    refreshSignal = Signal()    # trigger refresh
    # Emitted when drag-and-drop moves a folder or snippet to a new location
    folderMoved = Signal(str, str)   # old_path, new_path
    snippetMoved = Signal(dict, str) # entry dict, new_folder_path
    # Vault signals
    markFolderAsVault = Signal(object)    # folder QStandardItem
    removeFolderVault = Signal(object)    # folder QStandardItem
    vaultFolderClicked = Signal(str)      # folder path - emitted when a vault folder is clicked
    def __init__(self, main, parent=None):
        """
        Initialize the SnippetTable widget with model, proxy, and signal connections.

        Sets up the tree view with columns, sorting/filtering, drag-and-drop support,
        and connects signals for selection and data changes.

        Args:
            main (Any): Reference to the main application object.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        logger.info("Initializing SnippetTable")

        super().__init__(parent)
        self.setObjectName("SnippetTable")
        self.main = main
        self.parent = parent
        self.entries = []

        # Set Font Size
        self.setFont(self.main.medium_font_size)

        # Base model
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Label','Trigger','Enabled','Paste Style'])

        # Proxy for sorting/filtering
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setModel(self.proxy)

        # Set Column Width
        self.configure_columns()

        # Ensure we select rows
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

        # Drag & drop sorting
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)

        # Header sorting
        self.setSortingEnabled(True)

        # Track current selection
        #self.clicked.connect(self.on_click)
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)

        # Remove empty folders automatically
        self.model.rowsRemoved.connect(self.on_rows_removed)

        # Guard flag to suppress on_rows_removed during drag-and-drop moves
        self.is_dragging = False

        # Vault state
        self.vault_locked = False

        # Block expand-arrow clicks from opening locked/unconfigured vault folders.
        # mousePressEvent only catches clicks whose indexAt() lands on the item;
        # the branch/arrow area returns an invalid index, so we use the expanded
        # signal as a catch-all and immediately collapse if the vault is not open.
        self.expanded.connect(self.on_vault_expanded)

        logger.info("SnippetTable initialized successfully")

    def configure_columns(self):
        """
        Configure table column widths and header properties.

        Sets default widths for all columns while maintaining user resizability.
        Configures header font, resize mode, and allows section reordering.

        Returns:
            None
        """
        logger.info("Configuring column widths")

        try:
            header = self.header()
            header.setFont(self.main.small_font_size_bold)

            # Allow user resizing
            header.setSectionResizeMode(QHeaderView.Interactive)

            # Optional but recommended UX tweaks
            header.setStretchLastSection(False)
            header.setSectionsMovable(True)

            # Set default widths (these do NOT lock the columns)
            self.setColumnWidth(0, 180)  # Label
            self.setColumnWidth(1, 100)  # Trigger
            self.setColumnWidth(2, 80)   # Enabled
            self.setColumnWidth(3, 100)  # Paste Style
            self.setColumnWidth(4, 200)  # Tags

        except Exception as e:
            logger.error(f"Error configuring columns: {e}")

    def save_expansion_state(self) -> dict:
        """
        Save the current expansion state of all folders.

        Safely handles cases where QStandardItem objects have been deleted
        by Qt's C++ layer.

        Returns:
            dict: A dictionary mapping folder paths to their expansion state (bool).
        """
        expansion_state = {}
        for folder_path, folder_item in self.folders.items():
            try:
                src_idx = self.model.indexFromItem(folder_item)
                if src_idx.isValid():
                    proxy_idx = self.proxy.mapFromSource(src_idx)
                    expansion_state[folder_path] = self.isExpanded(proxy_idx)
            except RuntimeError:
                # QStandardItem was already deleted by Qt (e.g. after drag-drop)
                pass
        logger.debug(f"Saved expansion state for {len(expansion_state)} folders")
        return expansion_state

    def restore_expansion_state(self, expansion_state: dict) -> None:
        """
        Restore the previous expansion state of folders.

        Args:
            expansion_state (dict): Dictionary mapping folder paths to their desired state.

        Returns:
            None
        """
        for folder_path, should_expand in expansion_state.items():
            if folder_path in self.folders:
                folder_item = self.folders[folder_path]
                src_idx = self.model.indexFromItem(folder_item)
                if src_idx.isValid():
                    proxy_idx = self.proxy.mapFromSource(src_idx)
                    self.setExpanded(proxy_idx, should_expand)
        logger.debug(f"Restored expansion state for {len(expansion_state)} folders")

    def load_entries(self, entries):
        """
        Load and display snippet entries in the table organized by folders.

        Populates the tree view with snippets organized hierarchically by folder.
        Clears existing data, creates folder nodes, and adds snippet rows with
        associated metadata. Preserves folder expansion state if possible.

        Args:
            entries (list): List of dictionaries containing snippet data with keys:
                - folder (str): Folder name for organization.
                - label (str): Display name of the snippet.
                - trigger (str): Keyboard shortcut to activate the snippet.
                - snippet (str): The text content of the snippet.
                - enabled (bool): Whether the snippet is active.
                - paste_style (str): Paste method ("Clipboard" or "Keystroke").
                - tags (str): Comma-separated tags for the snippet.

        Returns:
            None
        """
        logger.info("Loading snippet entries into table")
        logger.debug("Entry count: %d", len(entries))

        # Save current expansion state before clearing (only if folders dict exists)
        previous_expansion_state = self.save_expansion_state() if hasattr(self, 'folders') and self.folders else {}

        self.entries = entries
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Label','Trigger','Enabled','Paste Style','Tags'])
        self.folders = {}  # folder_name > QStandardItem

        vault_is_setup = getattr(self, "vault_is_setup", False)
        vault_locked = getattr(self, "vault_locked", False)
        vault_folder_set = getattr(self, "vault_folder_set", set())
        vault_unlocked = vault_is_setup and not vault_locked

        for entry in entries:
            folder = entry.get('folder', 'Default')
            # Only show vault snippet rows when the vault is explicitly unlocked.
            # Covers both "set up and locked" and "not yet configured" states.
            if not vault_unlocked and folder in vault_folder_set:
                continue
            parent = self.get_or_create_folder(folder)

            label = entry.get('label', '')
            logger.debug("Adding snippet '%s' to folder '%s'", label, folder)

            label_item = QStandardItem(label)
            trigger_item = QStandardItem(entry.get('trigger',''))
            enabled_item = QStandardItem('On' if entry.get('enabled',False) else 'Off')
            style_item = QStandardItem(entry.get('paste_style',''))
            tags_item = QStandardItem(entry.get('tags',''))

            label_item.setData(entry, Qt.UserRole)
            parent.appendRow([label_item, trigger_item, enabled_item, style_item, tags_item])

        # Always show vault folders even when empty or vault not yet configured
        for vault_path in getattr(self, "vault_folder_set", set()):
            if vault_path not in self.folders:
                self.get_or_create_folder(vault_path)

        # Restore previous expansion state
        if previous_expansion_state:
            logger.info("Restoring previous folder expansion state")
            self.restore_expansion_state(previous_expansion_state)
        # Otherwise, check if we need to expand all folders based on settings
        elif self.main.settings["general"]["table_behavior"]["expand_folders_on_load"].get("value", False):
            logger.info("Expanding all folders on load as per settings")
            self.expandAll()    # Expand all folders on load.

        self.configure_columns()   # Resize
        logger.info("Snippet table populated")

    def get_or_create_folder(self, folder_path: str) -> QStandardItem:
        """
        Return the QStandardItem for the given slash-delimited folder path,
        creating intermediate parent folder nodes as needed.

        Args:
            folder_path (str): Full folder path, e.g. "default/sub/leaf".

        Returns:
            QStandardItem: The leaf folder item for the path.
        """
        if folder_path in self.folders:
            return self.folders[folder_path]

        vault_folders: set = getattr(self, "vault_folder_set", set())

        parts = folder_path.split("/")
        for i, part in enumerate(parts):
            current_path = "/".join(parts[: i + 1])
            if current_path in self.folders:
                continue

            folder_item = QStandardItem(part)
            folder_item.setData({"_type": "folder", "path": current_path}, Qt.UserRole)

            if current_path in vault_folders:
                self.apply_vault_icon(folder_item)

            empty_cols = [QStandardItem() for _ in range(4)]
            if i == 0:
                self.model.appendRow([folder_item] + empty_cols)
            else:
                parent_path = "/".join(parts[:i])
                self.folders[parent_path].appendRow([folder_item] + empty_cols)

            self.folders[current_path] = folder_item
            logger.debug("Created folder node '%s'", current_path)

        return self.folders[folder_path]

    def set_vault_folders(self, vault_folder_paths: list) -> None:
        """Update the set of vault folder paths (used for icons in load_entries)."""
        self.vault_folder_set = set(vault_folder_paths)

    def set_vault_lock_state(self, is_locked: bool, is_setup: bool = True) -> None:
        """Update locked state; collapse and clear vault folder rows when locking."""
        self.vault_locked = is_locked
        self.vault_is_setup = is_setup
        if is_locked and hasattr(self, "folders"):
            self.collapse_vault_folders()
            self.clear_vault_folder_children()

    def collapse_vault_folders(self) -> None:
        for folder_path in getattr(self, "vault_folder_set", set()):
            if folder_path not in getattr(self, "folders", {}):
                continue
            try:
                src_idx = self.model.indexFromItem(self.folders[folder_path])
                if src_idx.isValid():
                    self.setExpanded(self.proxy.mapFromSource(src_idx), False)
            except RuntimeError:
                pass

    def clear_vault_folder_children(self) -> None:
        """Remove all snippet rows from vault folder nodes so they cannot be seen while locked."""
        for folder_path in getattr(self, "vault_folder_set", set()):
            folder_item = getattr(self, "folders", {}).get(folder_path)
            if folder_item is None:
                continue
            try:
                row_count = folder_item.rowCount()
                if row_count:
                    folder_item.removeRows(0, row_count)
            except RuntimeError:
                pass

    def on_vault_expanded(self, proxy_index) -> None:
        """Immediately collapse any vault folder that is not currently unlocked.

        Qt's branch/expand-arrow click bypasses mousePressEvent's indexAt() check,
        so this signal handler is the authoritative guard against accidental expansion.
        """
        idx0 = proxy_index.sibling(proxy_index.row(), 0)
        src_idx = self.proxy.mapToSource(idx0)
        item = self.model.itemFromIndex(src_idx)
        idata = item.data(Qt.UserRole) if item else None
        if not isinstance(idata, dict) or idata.get("_type") != "folder":
            return
        folder_path = idata.get("path", "")
        vault_set = getattr(self, "vault_folder_set", set())
        if folder_path not in vault_set:
            return
        vault_is_setup = getattr(self, "vault_is_setup", False)
        vault_locked   = getattr(self, "vault_locked", False)
        if vault_is_setup and not vault_locked:
            return  # vault is unlocked - allow expansion
        self.collapse(proxy_index)

    def apply_vault_icon(self, item: QStandardItem) -> None:
        try:
            from PySide6.QtGui import QIcon
            from ui.theme_manager import ThemeManager
            is_locked = getattr(self, "vault_locked", True)
            is_setup = getattr(self, "vault_is_setup", False)
            # Show open lock only when vault is configured AND currently unlocked
            svg = "assets/icons/lock-open.svg" if (is_setup and not is_locked) else "assets/icons/lock.svg"
            tm = ThemeManager.get_instance()
            icon = QIcon(svg)
            if tm:
                icon = tm.recolor_icon(icon, tm.icon_color())
            item.setIcon(icon)
        except Exception:
            pass

    def refresh(self):
        """
        Reload the table data from the cached entries.

        Triggers a full reload of the parent configuration to refresh the table
        with current data from the database.

        Returns:
            None
        """
        logger.info("Refreshing snippet table data")
        
        if self.entries:
            self.parent.load_config()
        else:
            logger.debug("Refresh requested with no cached entries")

    def reload(self, entries):
        """
        Reload the table with a fresh snippet list.

        Clears and repopulates the entire table with the provided entries,
        useful for refreshing after external changes.

        Args:
            entries (list): List of snippet entry dictionaries to load.

        Returns:
            None
        """
        logger.info("Reloading snippet table")
        self.load_entries(entries)

    def on_click(self, proxy_idx):
        """
        Handle click event on a table item and emit the selected entry.

        Maps the proxy index to the source model, retrieves the entry data,
        and emits the entrySelected signal with snippet data if applicable.

        Args:
            proxy_idx (QModelIndex): The proxy model index of the clicked item.

        Returns:
            None
        """
        src_idx = self.proxy.mapToSource(proxy_idx)
        item = self.model.itemFromIndex(src_idx)
        if item is None:
            self.entrySelected.emit(None)
            return
        data = item.data(Qt.UserRole)

        logger.debug(f"Item Selected: {item}; Data: {data}; Src: {src_idx}")

        if isinstance(data, dict):
            if data.get("_type") == "folder":
                self.folderSelected.emit(data.get("path", ""))
            else:
                self.entrySelected.emit(data)
        else:
            self.entrySelected.emit(None)

    def on_selection_changed(self, selected, deselected):
        """
        Handle selection change events in the table.

        Processes selection model changes and delegates to on_click to emit
        the appropriate entrySelected signal.

        Args:
            selected (QItemSelection): The newly selected items.
            deselected (QItemSelection): The previously selected items.

        Returns:
            None
        """
        # grab the first index in the new selection
        indexes = selected.indexes()
        if not indexes:
            logger.debug("Selection cleared")
            self.entrySelected.emit(None)
            return

        # any column will do, we just need row/parent
        proxy_idx = indexes[0]
        logger.debug("Selection changed: %d indexes", len(indexes))
        self.on_click(proxy_idx)

    def contextMenuEvent(self, event):
        """
        Display the appropriate context menu based on the clicked item.

        Shows different context menus for empty space, folders, and snippets.
        Connects menu actions to corresponding signals.

        Args:
            event (QContextMenuEvent): The context menu event.

        Returns:
            None
        """
        logger.debug("Context menu requested")

        proxy_idx = self.indexAt(event.pos())

        if not proxy_idx.isValid():
            # Clicked on empty space; show empty context menu
            menu = EmptyContextMenu(self)
            menu.addFolderRequested.connect(lambda: self.addFolder.emit(None))
            menu.addSnippetRequested.connect(lambda: self.addSnippet.emit(None))
            menu.expandAllRequested.connect(self.expandAll)
            menu.collapseAllRequested.connect(self.collapseAll)
            menu.refreshRequested.connect(self.refreshSignal.emit)
            menu.exec(event.globalPos())
            return

        src_idx = self.proxy.mapToSource(proxy_idx)
        item = self.model.itemFromIndex(src_idx)
        if item is None:
            return
        data = item.data(Qt.UserRole)

        if isinstance(data, dict) and data.get("_type") == "folder":
            # Clicked on a folder; show folder context menu
            proxy_idx0 = proxy_idx.sibling(proxy_idx.row(), 0)
            is_expanded = self.isExpanded(proxy_idx0)
            folder_path = data.get("path", "")
            vault_set = getattr(self, "vault_folder_set", set())
            is_vault = folder_path in vault_set
            menu = FolderContextMenu(item, is_expanded, is_vault, self)
            menu.addItemRequested.connect(self.addSnippet.emit)
            menu.addFolderRequested.connect(self.addFolder.emit)
            menu.renameRequested.connect(self.renameFolder.emit)
            menu.deleteRequested.connect(self.deleteFolder.emit)
            menu.expandRequested.connect(lambda: self.setExpanded(proxy_idx0, True))
            menu.collapseRequested.connect(lambda: self.setExpanded(proxy_idx0, False))
            menu.markAsVaultRequested.connect(self.markFolderAsVault.emit)
            menu.removeVaultRequested.connect(self.removeFolderVault.emit)
        else:
            # Clicked on a snippet; show snippet context menu
            menu = SnippetContextMenu(data, self)
            menu.editRequested.connect(self.editSnippet.emit)
            menu.renameRequested.connect(self.renameSnippet.emit)
            menu.deleteRequested.connect(self.deleteSnippet.emit)

        menu.exec(event.globalPos())

    # Handlers for expanding/collapsing folders
    def expandAll(self):
        """
        Expand all folders in the table.

        Expands all top-level folder nodes to show all snippets.

        Returns:
            None
        """
        logger.debug("Expanding all folders in table")
        super().expandAll()

    def collapseAll(self):
        """
        Collapse all folders in the table.

        Collapses all top-level folder nodes to hide all snippets.

        Returns:
            None
        """
        logger.debug("Collapsing all folders in table")
        super().collapseAll()

    def isAnyFolderExpanded(self) -> bool:
        """
        Check if any top-level folder is currently expanded.

        Iterates through all top-level folder rows and checks their expansion state.

        Returns:
            bool: True if at least one folder is expanded, False otherwise.
        """
        for row in range(self.model.rowCount()):
            src_idx = self.model.index(row, 0)
            proxy_idx = self.proxy.mapFromSource(src_idx)

            if self.isExpanded(proxy_idx):
                return True

        return False

    # Helpers to manipulate UI state
    def clear_selection(self):
        """
        Clear the current selection in the table.

        Deselects all items, resetting the table to no active selection.

        Returns:
            None
        """
        logger.debug("Clearing table selection")
        self.clearSelection()

    def select_entry(self, entry):
        """
        Find and select the row matching the given entry's trigger.

        Recursively searches the tree model for a snippet matching the provided
        entry's trigger value and selects it if found.

        Args:
            entry (dict): Dictionary containing at least a 'trigger' key.

        Returns:
            None
        """
        logger.info(
            "Selecting entry by trigger: %s",
            entry.get('trigger')
        )

        def recurse(parent):
            for row in range(parent.rowCount()):
                label_item = parent.child(row,0)
                data = label_item.data(Qt.UserRole)

                if isinstance(data, dict) and data.get('trigger')==entry.get('trigger'):
                    logger.debug(
                        "Entry found in folder '%s'",
                        parent.text()
                    )

                    idx = label_item.index()
                    self.setCurrentIndex(self.proxy.mapFromSource(idx))
                    return True
                
                if recurse(label_item):
                    return True
            return False

        # search top‐level folders
        for i in range(self.model.rowCount()):
            folder = self.model.item(i,0)
            if recurse(folder):
                return
            
        logger.warning(
            "Entry not found during select_entry: %s",
            entry.get('trigger')
        )

    def current_entry(self):
        """
        Get the currently selected snippet entry.

        Returns the full snippet data dictionary for the currently selected row,
        or None if no valid snippet is selected.

        Returns:
            dict: The selected snippet entry dictionary, or None if invalid or not a snippet.
        """
        idx = self.currentIndex()
        if not idx.isValid():
            logger.warning("current_entry called with invalid index")
            return None
        
        # Always use column 0 where snippet data is stored
        # Fixes Issue #20
        idx = idx.sibling(idx.row(), 0)

        src_idx = self.proxy.mapToSource(idx)
        item = self.model.itemFromIndex(src_idx)
        if item is None:
            return None
        data = item.data(Qt.UserRole)

        if not isinstance(data, dict) or data.get("_type") == "folder":
            logger.debug("Current selection is not a snippet")
            return None

        return data

    def on_rows_removed(self, parent_idx: QModelIndex, start: int, end: int):
        """
        Automatically remove empty folders when all their children are deleted.

        Handles nested folders: if a sub-folder becomes empty it is removed,
        and if that causes the parent folder to become empty it is removed too.
        Skipped while a drag-and-drop is in progress to avoid premature removal.

        Args:
            parent_idx (QModelIndex): The parent folder index in model coordinates.
            start (int): The starting row of removed items.
            end (int): The ending row of removed items.

        Returns:
            None
        """
        # Never remove folders in the middle of an InternalMove drag-drop
        if self.is_dragging:
            return
        if not parent_idx.isValid():
            return
        parent = self.model.itemFromIndex(parent_idx)
        if parent and parent.rowCount() == 0:
            # Never remove vault folder nodes - they must always remain visible
            parent_data = parent.data(Qt.UserRole)
            if isinstance(parent_data, dict):
                folder_path = parent_data.get("path", "")
                if folder_path in getattr(self, "vault_folder_set", set()):
                    return
            logger.info("Removing empty folder: %s", parent.text())
            grandparent = parent.parent()
            if grandparent:
                grandparent.removeRow(parent.row())
            else:
                self.model.removeRow(parent.row())

    def mousePressEvent(self, event):
        """
        Handle mouse press events for folder expansion/collapse.

        Captures left mouse clicks to toggle folder expansion state without
        triggering item selection. Allows normal selection for non-folder rows.

        Args:
            event (QMouseEvent): The mouse press event.

        Returns:
            None
        """
        if event.button() == Qt.LeftButton:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                # Always operate on column 0 for expand or collapse
                idx0 = idx.sibling(idx.row(), 0)

                src_idx0 = self.proxy.mapToSource(idx0)
                item = self.model.itemFromIndex(src_idx0)

                # Folder rows are identified by _type == "folder" in UserRole
                idata = item.data(Qt.UserRole) if item else None
                if item and isinstance(idata, dict) and idata.get("_type") == "folder":
                    # Emit vault signal when a vault folder is clicked
                    folder_path = idata.get("path", "")
                    vault_set = getattr(self, "vault_folder_set", set())
                    if folder_path in vault_set:
                        self.vaultFolderClicked.emit(folder_path)
                        vault_is_setup = getattr(self, "vault_is_setup", False)
                        vault_locked   = getattr(self, "vault_locked", False)
                        if vault_is_setup and not vault_locked:
                            return super().mousePressEvent(event)  # unlocked - expand normally
                        return  # locked or not configured - block expansion

                    return super().mousePressEvent(event)

        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """
        Handle mouse double-click events.

        Toggles expand/collapse for folder rows. Discards double-clicks on snippet
        rows to prevent Qt's built-in inline editor from activating.

        Args:
            event (QMouseEvent): The mouse double-click event.

        Returns:
            None
        """
        if event.button() == Qt.LeftButton:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                idx0 = idx.sibling(idx.row(), 0)
                src_idx0 = self.proxy.mapToSource(idx0)
                item = self.model.itemFromIndex(src_idx0)
                idata = item.data(Qt.UserRole) if item else None
                if item and isinstance(idata, dict) and idata.get("_type") == "folder":
                    self.setExpanded(idx0, not self.isExpanded(idx0))
        event.accept()

    def dropEvent(self, event):
        """
        Handle drag-and-drop drops and persist path changes to the database.

        Instead of letting Qt perform an InternalMove (which destroys and
        recreates items, wiping UserRole data), we:

          1. Capture identity keys from the *pre-drop* item while UserRole is intact.
          2. Resolve the drop target and indicator to determine the new path.
          3. Emit the appropriate signal so the editor persists the change to the DB.
          4. Ignore the Qt-level move - the editor's reload will rebuild the tree
             from the database, which is the single source of truth.

        Args:
            event (QDropEvent): The drop event.

        Returns:
            None
        """
        logger.debug("dropEvent triggered")

        # Identify dragged item BEFORE the move
        sel = self.selectedIndexes()
        if not sel:
            logger.debug("dropEvent: no selected indexes, ignoring")
            event.ignore()
            return

        proxy_col0 = sel[0].sibling(sel[0].row(), 0)
        src_col0 = self.proxy.mapToSource(proxy_col0)
        pre_item = self.model.itemFromIndex(src_col0)
        if pre_item is None:
            logger.debug("dropEvent: pre_item is None, ignoring")
            event.ignore()
            return

        pre_data   = pre_item.data(Qt.UserRole)
        is_folder  = isinstance(pre_data, dict) and pre_data.get("_type") == "folder"
        is_snippet = isinstance(pre_data, dict) and "trigger" in pre_data

        if not is_folder and not is_snippet:
            logger.debug("dropEvent: item is neither folder nor snippet, ignoring")
            event.ignore()
            return

        # Stable keys captured while UserRole is still intact
        old_path     = pre_data.get("path", "")   if is_folder  else ""
        old_folder   = pre_data.get("folder", "") if is_snippet else ""
        item_segment = old_path.split("/")[-1]     if is_folder  else ""

        # Capture drop target info from the UNMODIFIED model
        drop_pos = event.position().toPoint()
        target_proxy_idx = self.indexAt(drop_pos)
        drop_indicator   = self.dropIndicatorPosition()

        logger.debug(
            "dropEvent: is_folder=%s, is_snippet=%s, old_path='%s', old_folder='%s', "
            "target_valid=%s, drop_indicator=%s",
            is_folder, is_snippet, old_path, old_folder,
            target_proxy_idx.isValid(), drop_indicator,
        )

        # Do NOT call super().dropEvent() - we handle the move ourselves via
        # the database. The editor's reload will rebuild the tree from DB.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()

        if is_folder:
            new_path = self.resolve_drop_parent_path(
                target_proxy_idx, drop_indicator, item_segment
            )
            logger.debug("dropEvent folder: new_path='%s', old_path='%s'", new_path, old_path)
            if new_path and new_path != old_path:
                logger.info("Folder drag-moved: '%s' -> '%s'", old_path, new_path)
                self.folderMoved.emit(old_path, new_path)

        elif is_snippet:
            new_folder = self.resolve_drop_parent_path(
                target_proxy_idx, drop_indicator, None
            )
            logger.debug("dropEvent snippet: new_folder='%s', old_folder='%s'", new_folder, old_folder)
            if new_folder is None:
                logger.warning(
                    "Snippet '%s' dropped at root - ignoring",
                    pre_data.get("trigger"),
                )
                return

            if new_folder != old_folder:
                # Snippet moved to a different folder
                logger.info(
                    "Snippet '%s' drag-moved: '%s' -> '%s'",
                    pre_data.get("trigger"), old_folder, new_folder,
                )
                self.snippetMoved.emit(pre_data, new_folder)
            else:
                logger.debug("dropEvent snippet: same folder drop ignored (no reordering)")

    # Path helpers
    def resolve_drop_parent_path(
        self,
        target_proxy_idx: QModelIndex,
        drop_indicator,
        item_segment: str | None,
    ) -> str | None:
        """
        Determine the new parent path for a drag-and-drop move using the
        pre-drop target index and Qt drop indicator.

        Using the drop target captured *before* ``super().dropEvent()`` is more
        reliable than inspecting ``currentIndex()`` afterward, because Qt clears
        the selection when an item is placed at root level via InternalMove.

        Args:
            target_proxy_idx: Proxy index of the item under the cursor before
                the drop.
            drop_indicator: ``QAbstractItemView.DropIndicatorPosition`` value.
            item_segment: The dragged folder's own name segment (for folders),
                or ``None`` for snippets.

        Returns:
            - Folders (``item_segment`` provided): the full new path string,
              e.g. ``"parent/sub"`` or just ``"sub"`` for a root-level drop.
            - Snippets (``item_segment`` is ``None``): the destination folder
              path string, or ``None`` if the destination is root (snippets
              cannot live at root level).
        """
        is_folder_drag = item_segment is not None

        # Dropped on the empty viewport; root level
        if not target_proxy_idx.isValid() or drop_indicator == QAbstractItemView.OnViewport:
            return item_segment if is_folder_drag else None

        target_col0 = target_proxy_idx.sibling(target_proxy_idx.row(), 0)
        target_src  = self.proxy.mapToSource(target_col0)
        target_item = self.model.itemFromIndex(target_src)
        if target_item is None:
            return item_segment if is_folder_drag else None

        target_data = target_item.data(Qt.UserRole)

        if drop_indicator == QAbstractItemView.OnItem:
            # Dropped directly onto a folder; becomes a child of that folder
            if isinstance(target_data, dict) and target_data.get("_type") == "folder":
                parent_path = target_data.get("path", target_item.text())
            else:
                # Dropped onto a snippet; use its parent folder
                p = target_item.parent()
                if p is None:
                    return item_segment if is_folder_drag else None
                pd = p.data(Qt.UserRole)
                parent_path = pd.get("path", p.text()) if isinstance(pd, dict) else p.text()
        else:
            # AboveItem / BelowItem; same level as the target (target's parent)
            p = target_item.parent()
            if p is None:
                # Target is a root-level item.
                if is_folder_drag:
                    # Folder drag: place at root level
                    return item_segment

                # Snippet drag: snippets cannot live at root level.
                # If the target is itself a folder, treat the drop as landing
                # *inside* that folder so the move isn't silently ignored when
                # the cursor is slightly above/below the row centre.
                if isinstance(target_data, dict) and target_data.get("_type") == "folder":
                    parent_path = target_data.get("path", target_item.text())
                    logger.debug(
                        "resolve_drop_parent_path: AboveItem/BelowItem on root folder "
                        "'%s' - treating as OnItem for snippet",
                        parent_path,
                    )
                else:
                    return None
            else:
                pd = p.data(Qt.UserRole)
                parent_path = pd.get("path", p.text()) if isinstance(pd, dict) else p.text()

        if is_folder_drag:
            return parent_path + "/" + item_segment
        return parent_path

    def compute_item_path(self, item: QStandardItem) -> str:
        """
        Walk up the parent chain to build the full slash-delimited folder path.

        Each folder item stores only its local segment as ``text()``, so
        ascending via ``parent()`` reconstructs the full nested path.

        Args:
            item (QStandardItem): A folder item in the source model.

        Returns:
            str: Full path, e.g. ``"personal/drafts/work"``.
        """
        parts: list[str] = []
        current = item
        while current is not None:
            parts.append(current.text())
            current = current.parent()
        parts.reverse()
        return "/".join(parts)

    def applyStyles(self):
        """
        Apply font and size styling to the table, header, and all items.

        Returns:
            None
        """
        logger.debug("Applying SnippetTable styles")

        try:
            self.setFont(self.main.medium_font_size)

            h = self.header()
            if h:
                h.setFont(self.main.medium_font_size)
                h.viewport().update()

            def set_item_font(item):
                item.setFont(self.main.medium_font_size)
                for i in range(item.rowCount()):
                    set_item_font(item.child(i))

            source_model = self.model if hasattr(self, "model") else None
            if source_model:
                for i in range(source_model.rowCount()):
                    root_item = source_model.item(i, 0)
                    if root_item:
                        set_item_font(root_item)

            self.viewport().update()
        except Exception:
            pass
