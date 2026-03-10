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
        """
        Initialize the SnippetContextMenu.

        Args:
            entry (dict): The snippet entry data dictionary.
            parent (QWidget): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.entry = entry
        self._build()

    def _build(self):
        """
        Build the snippet context menu with all available snippet actions.

        Adds menu items for editing, renaming, and deleting the snippet.

        Returns:
            None
        """
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
