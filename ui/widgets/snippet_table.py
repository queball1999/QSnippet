
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
    addFolder = Signal(QStandardItem)  # parent folder or None
    addSnippet = Signal(QStandardItem)  # parent folder
    editSnippet = Signal(dict)           # entry data
    renameFolder = Signal(QStandardItem)  # folder item
    renameSnippet = Signal(dict)           # entry data
    deleteFolder = Signal(QStandardItem)  # folder item
    deleteSnippet = Signal(dict)           # entry data
    entrySelected = Signal(dict)           # when a snippet is clicked
    refreshSignal = Signal()    # trigger refresh
    # Emitted when drag-and-drop moves a folder or snippet to a new location
    folderMoved = Signal(str, str)   # old_path, new_path
    snippetMoved = Signal(dict, str) # entry dict, new_folder_path

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
        self.main = main
        self.parent = parent
        self._entries = []

        # Set Font Size
        self.setFont(self.main.small_font_size)

        # Base model
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Label','Trigger','Enabled','Paste Style'])

        # Proxy for sorting/filtering
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setModel(self.proxy)

        # Set Column Width
        self._configure_columns()

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
        #self.clicked.connect(self._on_click)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Remove empty folders automatically
        self.model.rowsRemoved.connect(self._on_rows_removed)

        # Guard flag to suppress _on_rows_removed during drag-and-drop moves
        self._is_dragging = False

        logger.info("SnippetTable initialized successfully")

    def _configure_columns(self):
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
            header.setFont(QFont("Arial", 12, QFont.Bold))

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

    def load_entries(self, entries):
        """
        Load and display snippet entries in the table organized by folders.

        Populates the tree view with snippets organized hierarchically by folder.
        Clears existing data, creates folder nodes, and adds snippet rows with
        associated metadata. Expands folders based on settings.

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

        if not entries:
            logger.debug("No entries were loaded")
            return      # if none, return
        
        self.entries = entries
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Label','Trigger','Enabled','Paste Style','Tags'])
        self.folders = {}  # folder_name > QStandardItem

        for entry in entries:
            folder = entry.get('folder', 'Default')
            parent = self._get_or_create_folder(folder)

            # Create child snippet row
            label = entry.get('label', '')
            logger.debug("Adding snippet '%s' to folder '%s'", label, folder)

            label_item = QStandardItem(label)
            trigger_item = QStandardItem(entry.get('trigger',''))
            enabled_item = QStandardItem('On' if entry.get('enabled',False) else 'Off')
            style_item = QStandardItem(entry.get('paste_style',''))
            tags_item = QStandardItem(entry.get('tags',''))

            # Store full entry dict on first column
            label_item.setData(entry, Qt.UserRole)

            parent.appendRow([label_item, trigger_item, enabled_item, style_item, tags_item])

        # Check if we need to expand all folders on load
        # Default to False if setting missing
        if self.main.settings["general"]["startup_behavior"]["expand_folders_on_load"].get("value", False):
            logger.info("Expanding all folders on load as per settings")
            self.expandAll()    # Expand all folders on load.

        self._configure_columns()   # Resize
        logger.info("Snippet table populated")

    def _get_or_create_folder(self, folder_path: str) -> QStandardItem:
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

        parts = folder_path.split("/")
        for i, part in enumerate(parts):
            current_path = "/".join(parts[: i + 1])
            if current_path in self.folders:
                continue

            folder_item = QStandardItem(part)
            folder_item.setData({"_type": "folder", "path": current_path}, Qt.UserRole)

            empty_cols = [QStandardItem() for _ in range(4)]
            if i == 0:
                self.model.appendRow([folder_item] + empty_cols)
            else:
                parent_path = "/".join(parts[:i])
                self.folders[parent_path].appendRow([folder_item] + empty_cols)

            self.folders[current_path] = folder_item
            logger.debug("Created folder node '%s'", current_path)

        return self.folders[folder_path]

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

    def _on_click(self, proxy_idx):
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
        data = item.data(Qt.UserRole)

        logger.debug(f"Item Selected: {item}; Data: {data}; Src: {src_idx}")

        if isinstance(data, dict):
            self.entrySelected.emit(data)
        else:
            self.entrySelected.emit(None)

    def _on_selection_changed(self, selected, deselected):
        """
        Handle selection change events in the table.

        Processes selection model changes and delegates to _on_click to emit
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
        self._on_click(proxy_idx)

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
        data = item.data(Qt.UserRole)

        if isinstance(data, dict) and data.get("_type") == "folder":
            # Clicked on a folder; show folder context menu
            menu = FolderContextMenu(item, self)
            menu.addItemRequested.connect(self.addSnippet.emit)
            menu.addFolderRequested.connect(self.addFolder.emit)
            menu.renameRequested.connect(self.renameFolder.emit)
            menu.deleteRequested.connect(self.deleteFolder.emit)
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
        data = item.data(Qt.UserRole)

        if not isinstance(data, dict) or data.get("_type") == "folder":
            logger.debug("Current selection is not a snippet")
            return None

        return data

    def _on_rows_removed(self, parent_idx: QModelIndex, start: int, end: int):
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
        if self._is_dragging:
            return
        if not parent_idx.isValid():
            return
        parent = self.model.itemFromIndex(parent_idx)
        if parent and parent.rowCount() == 0:
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
                    # Let Qt handle clicks in the "branch" area (arrow and indentation)
                    rect = self.visualRect(idx0)

                    # The branch area is basically the left gutter before the text.
                    # indentation() is the per level indent. Add a little extra for the arrow glyph.
                    branch_area_right = rect.left() + self.indentation() + 24

                    if event.pos().x() <= branch_area_right:
                        return super().mousePressEvent(event)

                    # Click was on the row content area, toggle expansion ourselves
                    self.setExpanded(idx0, not self.isExpanded(idx0))
                    return super().mousePressEvent(event)

        return super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """
        Handle mouse double-click events.

        Captures and discards double-click events to prevent default editor activation.

        Args:
            event (QMouseEvent): The mouse double-click event.

        Returns:
            None
        """
        event.accept()

    def dropEvent(self, event):
        """
        Handle drag-and-drop drops and persist path changes to the database.

        Qt's InternalMove serialises the dragged item via MIME and recreates it
        at the destination, which can wipe custom UserRole data on the moved item.
        We therefore:

          1. Capture identity keys from the *pre-drop* item while UserRole is intact.
          2. Let Qt perform the in-model move (``super().dropEvent``).
          3. Use ``currentIndex()`` - Qt keeps selection on the moved item -
             to locate it at its new position.
          4. Walk up the *stationary* parent's intact UserRole to derive the new path.
          5. Emit the appropriate signal so the editor persists the change to the DB.

        Args:
            event (QDropEvent): The drop event.

        Returns:
            None
        """
        # Identify dragged item BEFORE the move
        sel = self.selectedIndexes()
        if not sel:
            super().dropEvent(event)
            return

        proxy_col0 = sel[0].sibling(sel[0].row(), 0)
        src_col0 = self.proxy.mapToSource(proxy_col0)
        pre_item = self.model.itemFromIndex(src_col0)
        if pre_item is None:
            super().dropEvent(event)
            return

        pre_data   = pre_item.data(Qt.UserRole)
        is_folder  = isinstance(pre_data, dict) and pre_data.get("_type") == "folder"
        is_snippet = isinstance(pre_data, dict) and "trigger" in pre_data

        if not is_folder and not is_snippet:
            super().dropEvent(event)
            return

        # Stable keys captured before Qt destroys + recreates the item
        old_path     = pre_data.get("path", "")   if is_folder  else ""
        old_folder   = pre_data.get("folder", "") if is_snippet else ""
        item_segment = old_path.split("/")[-1]     if is_folder  else ""

        # Capture drop target info BEFORE the drop
        # currentIndex() after super().dropEvent() is unreliable for root-level
        # drops: Qt clears the selection when a folder becomes a top-level row
        # via InternalMove, so the post-drop lookup silently fails and the
        # folderMoved signal is never emitted.  Resolving from the pre-drop
        # event target avoids that race entirely.
        target_proxy_idx = self.indexAt(event.pos())
        drop_indicator   = self.dropIndicatorPosition()

        # Perform the drop
        self._is_dragging = True
        super().dropEvent(event)
        self._is_dragging = False

        if is_folder:
            new_path = self._resolve_drop_parent_path(
                target_proxy_idx, drop_indicator, item_segment
            )
            if new_path and new_path != old_path:
                logger.info("Folder drag-moved: '%s'; '%s'", old_path, new_path)
                self.folderMoved.emit(old_path, new_path)

        elif is_snippet:
            new_folder = self._resolve_drop_parent_path(
                target_proxy_idx, drop_indicator, None
            )
            if new_folder is None:
                logger.warning(
                    "Snippet '%s' dropped at root - ignoring",
                    pre_data.get("trigger"),
                )
                return
            if new_folder != old_folder:
                logger.info(
                    "Snippet '%s' drag-moved: '%s'; '%s'",
                    pre_data.get("trigger"), old_folder, new_folder,
                )
                self.snippetMoved.emit(pre_data, new_folder)

    # Path helpers
    def _resolve_drop_parent_path(
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
                # Target is a root item; new item goes to root too
                return item_segment if is_folder_drag else None
            pd = p.data(Qt.UserRole)
            parent_path = pd.get("path", p.text()) if isinstance(pd, dict) else p.text()

        if is_folder_drag:
            return parent_path + "/" + item_segment
        return parent_path

    def _compute_item_path(self, item: QStandardItem) -> str:
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
        Apply styling properties to the table and its widgets.

        Sets fonts, sizes, and updates the stylesheet for consistent appearance
        with the rest of the application.

        Returns:
            None
        """
        logger.debug("Applying SnippetTable styles")

        # Font Sizing
        self.setFont(self.main.small_font_size)

        # Button Sizing

        # Widget Styling

        # StyleSheet
        # self.update_stylesheet()

        self.layout().invalidate()
        self.update()

    def update_stylesheet(self):
        """
        Apply the CSS stylesheet to table components.

        Updates styling rules for the tree view and its related widgets.

        Returns:
            None
        """
        self.setStyleSheet(""" 

        """)
