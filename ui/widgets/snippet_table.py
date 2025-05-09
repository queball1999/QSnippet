import yaml
from pathlib import Path
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal

class SnippetTable(QTreeWidget):
    # Emits the selected entry dict, or None if nothing selected or folder
    entrySelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(['Label', 'Trigger', 'Enabled', 'Paste Style'])
        self.current_item = None
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def load_entries(self, entries):
        """
        Populate the tree with a list of snippet entries.
        Each entry is a dict with keys: folder, label, trigger, snippet, enabled, paste_style
        """
        self.clear()
        self.folder_items = {}
        for entry in entries:
            folder = entry.get('folder', 'Default')
            if folder not in self.folder_items:
                parent = QTreeWidgetItem(self, [folder])
                parent.setFirstColumnSpanned(True)
                parent.setData(0, Qt.UserRole, None)
                self.addTopLevelItem(parent)
                self.folder_items[folder] = parent
            parent = self.folder_items[folder]
            item = QTreeWidgetItem(parent, [
                entry.get('label', ''),
                entry.get('trigger', ''),
                'On' if entry.get('enabled', False) else 'Off',
                entry.get('paste_style', '')
            ])
            item.setData(0, Qt.UserRole, entry)
            parent.addChild(item)
        self.expandAll()

    def _on_selection_changed(self):
        items = self.selectedItems()
        if not items:
            self.entrySelected.emit(None)
            return
        item = items[0]
        entry = item.data(0, Qt.UserRole)
        if isinstance(entry, dict):
            self.current_item = item
            self.entrySelected.emit(entry)
        else:
            self.entrySelected.emit(None)

    def clear_selection(self):
        self.clearSelection()
        self.current_item = None
        self.entrySelected.emit(None)

    def select_entry(self, entry):
        # Find item matching entry['trigger'] and select it
        def recurse(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                data = child.data(0, Qt.UserRole)
                if isinstance(data, dict) and data.get('trigger') == entry.get('trigger'):
                    self.setCurrentItem(child)
                    return True
                if recurse(child):
                    return True
            return False
        for idx in range(self.topLevelItemCount()):
            top = self.topLevelItem(idx)
            if recurse(top):
                break

    def current_entry(self):
        if self.current_item:
            return self.current_item.data(0, Qt.UserRole)
        return None
