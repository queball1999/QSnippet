from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Signal, QObject


class SnippetContextMenu(QMenu):
    """
    SnippetContextMenu is used when right-clicking on a snippet in the main UI.
    It provides options to edit, rename, or delete the snippet.
    """
    editRequested   = Signal(dict)
    renameRequested = Signal(dict)
    deleteRequested = Signal(dict)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._build()

    def _build(self):
        self.addAction(
            "Edit Item",
            lambda: self.editRequested.emit(self.entry)
        )
        self.addAction(
            "Rename Item",
            lambda: self.renameRequested.emit(self.entry)
        )
        self.addSeparator()
        self.addAction(
            "Delete Item",
            lambda: self.deleteRequested.emit(self.entry)
        )
