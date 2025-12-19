
import logging
from PySide6.QtWidgets import (
    QTreeView, QMenu, QAbstractItemView, QHeaderView
)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import (
    Qt, Signal, QModelIndex, QSortFilterProxyModel
)

logger = logging.getLogger(__name__)

class SnippetTable(QTreeView):
    # Signals for context‐menu actions
    addFolder = Signal(QStandardItem)  # parent folder or None
    addSnippet = Signal(QStandardItem)  # parent folder
    addSubFolder = Signal(QStandardItem)  # parent folder
    editSnippet = Signal(dict)           # entry data
    renameFolder = Signal(QStandardItem)  # folder item
    renameSnippet = Signal(dict)           # entry data
    deleteFolder = Signal(QStandardItem)  # folder item
    deleteSnippet = Signal(dict)           # entry data
    entrySelected = Signal(dict)           # when a snippet is clicked
    refreshSignal = Signal()    # trigger refresh

    def __init__(self, main, parent=None):
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

        logger.info("SnippetTable initialized successfully")

    def _configure_columns(self):
        """ Resize columns to set width. """
        # should we capture this and save it in config?
        # or should it be a configurable setting?
        logger.info("Configuring column widths")

        try:
            header = self.header()
            header.setSectionResizeMode(QHeaderView.Fixed)

            self.setColumnWidth(0, 180)
            self.setColumnWidth(1, 100)
            self.setColumnWidth(2, 80)
            self.setColumnWidth(3, 100)
            self.setColumnWidth(4, 200)
        except Exception as e:
            logger.error(f"An error occured while configuring columns: {e}")
            return None

    def load_entries(self, entries):
        """
        entries: list of dicts with keys
          folder, label, trigger, snippet, enabled (bool), paste_style
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
            folder = entry.get('folder','Default')
            
            if folder not in self.folders:
                folder_item = QStandardItem(folder)
                # mark it as a folder
                folder_item.setData(None, Qt.UserRole)

                # Just one call to appendRow, supplying one item per column:
                self.model.appendRow([
                    folder_item,
                    QStandardItem(),
                    QStandardItem(),
                    QStandardItem(),
                    QStandardItem()
                ])
                self.folders[folder] = folder_item

            parent = self.folders[folder]

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

        self.expandAll()    # Expand all folders on load. (Make setting?)
        self._configure_columns()   # Resize
        logger.info("Snippet table populated")

    def refresh(self):
        """ Reload the table data. """
        logger.info("Refreshing snippet table data")
        
        if self.entries:
            self.parent.load_config()
        else:
            logger.debug("Refresh requested with no cached entries")

    def reload(self, entries):
        """Reload the table with a fresh snippet list"""
        logger.info("Reloading snippet table")
        self.load_entries(entries)

    def _on_click(self, proxy_idx):
        src_idx = self.proxy.mapToSource(proxy_idx)
        item = self.model.itemFromIndex(src_idx)
        data = item.data(Qt.UserRole)

        logger.debug(f"Item Selected: {item}; Data: {data}; Src: {src_idx}")

        if isinstance(data, dict):
            self.entrySelected.emit(data)
        else:
            self.entrySelected.emit(None)

    def _on_selection_changed(self, selected, deselected):
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
        logger.debug("Context menu requested")

        proxy_idx = self.indexAt(event.pos())
        menu = QMenu(self)

        if not proxy_idx.isValid():
            # whitespace
            logger.debug("Context menu on empty area")

            menu.addAction('Add Folder', lambda: self.addFolder.emit(None))
            menu.addAction('Add Snippet', lambda: self.addSnippet.emit(None))
            menu.addSeparator()
            menu.addAction('Expand All', None)
            menu.addAction('Collapse All', None)
            menu.addSeparator()
            menu.addAction('Refresh', self.refreshSignal.emit)

        else:
            logger.debug("Context menu on item")
            src_idx = self.proxy.mapToSource(proxy_idx)
            item = self.model.itemFromIndex(src_idx)
            data = item.data(Qt.UserRole)

            if data is None:
                # folder row
                menu.addAction('Add Item', lambda item=item: self.addSnippet.emit(item))
                menu.addAction('Add Sub-Folder', lambda item=item: self.addSubFolder.emit(item))
                menu.addSeparator()
                menu.addAction("Rename Folder", lambda item=item: self.renameFolder.emit(item))
                menu.addAction('Delete Folder', lambda: self.deleteFolder.emit(item))
            else:
                # snippet row
                menu.addAction('Edit Item', lambda data=data: self.editSnippet.emit(data))
                menu.addAction('Rename Item', lambda data=data: self.renameSnippet.emit(data))
                menu.addAction('Delete Item', lambda data=data: self.deleteSnippet.emit(data))

        menu.exec(event.globalPos())

    def clear_selection(self):
        logger.debug("Clearing table selection")
        self.clearSelection()

    def select_entry(self, entry):
        """Find and select the row matching entry['trigger']."""
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
        """ Return the current index in the table """
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

        if not isinstance(data, dict):
            logger.debug("Current selection is not a snippet")
            return None

        return data

    def _on_rows_removed(self, parent_idx: QModelIndex, start: int, end: int):
        """
        If a folder loses all its children, delete the folder automatically.
        parent_idx is in model coordinates.
        """
        if not parent_idx.isValid():
            return
        parent = self.model.itemFromIndex(parent_idx)
        if parent and parent.rowCount()==0:
            logger.info(
                "Removing empty folder: %s",
                parent.text()
            )
            # remove the folder
            self.model.removeRow(parent.row())

    def applyStyles(self):
        logger.debug("Applying SnippetTable styles")

        # Font Sizing
        self.setFont(self.main.small_font_size)

        # Button Sizing

        # Widget Styling

        # StyleSheet
        self.update_stylesheet()

        self.layout().invalidate()
        self.update()

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        logger.debug("Updating SnippetTable stylesheet")
        #self.setStyleSheet(f""" """)