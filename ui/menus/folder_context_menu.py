from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Signal


class FolderContextMenu(QMenu):
    """
    FolderContextMenu is used when right-clicking on a folder in the main UI.
    It provides options to add items, rename a folder, or delete a folder.
    """
    addItemRequested    = Signal(object)
    addFolderRequested  = Signal(object)
    renameRequested     = Signal(object)
    deleteRequested     = Signal(object)

    def __init__(self, folder_item, parent=None):
        super().__init__(parent)
        self.folder_item = folder_item
        self._build()

    def _build(self):
        self.addAction(
            "Add Item",
            lambda: self.addItemRequested.emit(self.folder_item)
        )
        # To Remove: sub folder functionality
        """ self.addAction(
            "Add Sub-Folder",
            lambda: self.addFolderRequested.emit(self.folder_item)
        ) """
        self.addAction(
            "Rename Folder",
            lambda: self.renameRequested.emit(self.folder_item)
        )
        self.addSeparator()
        self.addAction(
            "Delete Folder",
            lambda: self.deleteRequested.emit(self.folder_item)
        )
