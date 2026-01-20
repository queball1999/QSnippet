from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Signal


class EmptyContextMenu(QMenu):
    """
    EmptyContextMenu is used when right-clicking on empty space in the main UI.
    It provides options to add new folders or snippets, as well as refresh the view.
    """
    addFolderRequested  = Signal()
    addSnippetRequested = Signal()
    expandAllRequested = Signal()
    collapseAllRequested = Signal()
    refreshRequested    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        self.addAction("Add Folder", self.addFolderRequested.emit)
        self.addAction("Add Snippet", self.addSnippetRequested.emit)
        self.addSeparator()
        self.addAction("Expand All", self.expandAllRequested.emit)
        self.addAction("Collapse All", self.collapseAllRequested.emit)
        self.addSeparator()
        self.addAction("Refresh", self.refreshRequested.emit)
