from PySide6.QtWidgets import (
    QComboBox, QStyledItemDelegate, QListView, 
    QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal



class ComboListView(QListView):
    def __init__(self, parent_combo) -> None:
        """
        Initialize the ComboListView.

        Stores a reference to the parent combo box for delegated
        interaction handling.

        Args:
            parent_combo (Any): The associated combo box instance.

        Returns:
            None
        """
        super().__init__()
        self.parent_combo = parent_combo

    def mousePressEvent(self, event) -> None:
        """
        Handle mouse press events within the combo list view.

        Right-click displays a context menu, left-click toggles the
        check state without closing the popup, and other events are
        handled by the base implementation.

        Args:
            event (Any): The mouse event.

        Returns:
            None
        """ 
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

    def __init__(self, parent=None) -> None:
        """
        Initialize the CheckableComboBox.

        Configures the combo box to support checkable items, editable
        input for new tags, custom list view handling, and automatic
        text updates when item states change.

        Args:
            parent (Any): Optional parent widget.

        Returns:
            None
        """
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
        self.lineEdit().returnPressed.connect(self.onReturnPressed)

    def onReturnPressed(self) -> None:
        """
        Handle the return key press in the line edit.

        Adds any newly typed tags and updates the displayed text.

        Returns:
            None
        """
        self.addNewTagIfTyped()
        self.updateText()

    def addItem(self, text, data=None, checked=False) -> None:
        """
        Add a new checkable item to the combo box.

        Args:
            text (str): The display text for the item.
            data (Any): Optional associated data.
            checked (bool): Whether the item should be initially checked.

        Returns:
            None
        """
        super().addItem(text, data)
        item = self.model().item(self.count() - 1, 0)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def addItems(self, texts, checked=False) -> None:
        """
        Add multiple checkable items to the combo box.

        Args:
            texts (list): A list of item display texts.
            checked (bool): Whether the items should be initially checked.

        Returns:
            None
        """
        for text in texts:
            self.addItem(text, checked=checked)

    def handleItemPressed(self, index) -> None:
        """
        Toggle the check state of an item when clicked.

        Args:
            index (Any): The model index of the clicked item.

        Returns:
            None
        """
        item = self.model().itemFromIndex(index)
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def checkedItems(self) -> list:
        """
        Retrieve the texts of all checked items.

        Returns:
            list: A list of checked item texts.
        """
        return [
            self.itemText(i)
            for i in range(self.count())
            if self.model().item(i, 0).checkState() == Qt.Checked
        ]

    def setCheckedItems(self, items) -> None:
        """
        Set the checked state of items based on a list of strings.

        Args:
            items (list): A list of item texts to mark as checked.

        Returns:
            None
        """
        items = set(i.lower() for i in items)
        for i in range(self.count()):
            item = self.model().item(i, 0)
            item.setCheckState(
                Qt.Checked if item.text().lower() in items else Qt.Unchecked
            )

    def updateText(self) -> None:
        """
        Update the line edit text to reflect checked items.

        Displays no text if none are checked, a single item if only
        one is checked, or a comma-separated list if multiple are checked.

        Returns:
            None
        """
        checked = self.checkedItems()
        if not checked:
            self.lineEdit().setText("")
        elif len(checked) == 1:
            self.lineEdit().setText(checked[0])
        else:
            self.lineEdit().setText(", ".join(checked))

    def addNewTagIfTyped(self) -> None:
        """
        Add new tags entered by the user and mark them as checked.

        Splits the current text by commas, checks existing matching tags,
        and adds new ones if they do not already exist.

        Returns:
            None
        """
        raw_text = self.currentText().strip()
        if not raw_text:
            return

        # Split into candidate tags
        candidates = [t.strip() for t in raw_text.split(",") if t.strip()]
        existing = {self.itemText(i).lower() for i in range(self.count())}

        # print(f"candidates - {candidates}")
        # print(f"existing - {existing}")

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

    def showContextMenu(self, index, globalPos) -> None:
        """
        Display a context menu for deleting a tag.

        Prompts the user for confirmation before removing the tag
        and emitting the tagDeleteRequested signal.

        Args:
            index (Any): The model index of the selected item.
            globalPos (Any): The global screen position for the menu.

        Returns:
            None
        """
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
