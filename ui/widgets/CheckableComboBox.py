from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QListView, QMenu, QMessageBox
from PySide6.QtCore import Qt, Signal


class ComboListView(QListView):
    def __init__(self, parent_combo):
        super().__init__()
        self.parent_combo = parent_combo

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return super().mousePressEvent(event)

        if event.button() == Qt.RightButton:
            # right-click → show context menu
            self.parent_combo.showContextMenu(index, event.globalPos())
            return  # swallow right-click
        elif event.button() == Qt.LeftButton:
            # left-click → toggle check state
            self.parent_combo.handleItemPressed(index)
            return  # swallow left-click (don’t close popup)

        return super().mousePressEvent(event)
    
class CheckableComboBox(QComboBox):
    tagDeleteRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setPlaceholderText("Select tags...")
        self.setItemDelegate(QStyledItemDelegate())  # default delegate
        self.tagDeleted = None  # assign a callback externally

        # Use a QListView so we can intercept clicks
        view = ComboListView(self)
        self.setView(view)

        # Connect dataChanged to updateText
        # Forces update on any change and removes need to call anywhere else.
        self.model().dataChanged.connect(lambda *_: self.updateText())

        # Connect return press to addNewTagIfTyped
        self.lineEdit().returnPressed.connect(self._onReturnPressed)

    def _onReturnPressed(self):
        self.addNewTagIfTyped()
        self.updateText()

    def addItem(self, text, data=None, checked=False):
        """Add a new item, optionally defaulting to checked."""
        super().addItem(text, data)
        item = self.model().item(self.count() - 1, 0)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def addItems(self, texts, checked=False):
        for text in texts:
            self.addItem(text, checked=checked)

    def handleItemPressed(self, index):
        """Toggle check state when an item is clicked."""
        item = self.model().itemFromIndex(index)
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def checkedItems(self):
        """Return a list of checked item texts."""
        return [
            self.itemText(i)
            for i in range(self.count())
            if self.model().item(i, 0).checkState() == Qt.Checked
        ]

    def setCheckedItems(self, items):
        """Check/uncheck items based on provided list of strings."""
        items = set(i.lower() for i in items)
        for i in range(self.count()):
            item = self.model().item(i, 0)
            item.setCheckState(
                Qt.Checked if item.text().lower() in items else Qt.Unchecked
            )

    def updateText(self):
        """Update the line edit text based on checked items."""
        checked = self.checkedItems()
        if not checked:
            self.lineEdit().setText("")
        elif len(checked) == 1:
            self.lineEdit().setText(checked[0])
        else:
            self.lineEdit().setText(", ".join(checked))

    def addNewTagIfTyped(self):
        print("addNewTagIfTyped")
        """If the user typed one or more new tags and pressed Enter, add them checked."""
        raw_text = self.currentText().strip()
        if not raw_text:
            return

        # Split into candidate tags
        candidates = [t.strip() for t in raw_text.split(",") if t.strip()]
        existing = {self.itemText(i).lower() for i in range(self.count())}

        print(f"candidates - {candidates}")
        print(f"existing - {existing}")

        added_any = False
        for tag in candidates:
            if tag.lower() in existing:
                # Already present → just check it
                for i in range(self.count()):
                    item = self.model().item(i, 0)
                    if item.text().lower() == tag.lower():
                        item.setCheckState(Qt.Checked)
            else:
                # New tag → add and check
                self.addItem(tag, checked=True)
                existing.add(tag.lower())
                added_any = True

        if added_any or candidates:
            self.updateText()

    def showContextMenu(self, index, globalPos):
        """Show context menu with delete option; ask for confirmation."""
        item = self.model().itemFromIndex(index)
        if not item:
            return
        menu = QMenu(self)
        act_delete = menu.addAction(f"Delete tag '{item.text()}'")
        chosen = menu.exec(globalPos)

        if chosen == act_delete:
            tag = item.text()
            confirm = self.parent().main.message_box.question(
                f"Delete tag '{tag}' from all snippets?",
                title="Confirm Deletion"
            )

            if confirm == QMessageBox.Yes:
                self.removeItem(index.row())
                self.tagDeleteRequested.emit(tag)
                self.updateText()
