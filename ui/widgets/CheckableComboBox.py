from PySide6.QtWidgets import (
    QComboBox, QStyledItemDelegate, QListView, 
    QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QStandardItemModel, QStandardItem



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
            # right-click; show context menu
            self.parent_combo.showContextMenu(index, event.globalPos())
            return  # swallow right-click
        elif event.button() == Qt.LeftButton:
            # left-click; toggle check state
            self.parent_combo.handleItemPressed(index)
            return  # swallow left-click (don’t close popup)

        return super().mousePressEvent(event)
    
class CheckableComboBox(QComboBox):
    tagDeleteRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        """
        Initialize the CheckableComboBox.

        Configures the combo box to support checkable items, editable
        input for new tags, and custom list view handling. The popup
        is only shown when the user explicitly clicks the widget.

        Args:
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.setEditable(True)
        
        # Guard: popup is ONLY allowed when the user explicitly clicks the widget
        self._popup_allowed = False
        
        # Guard: suppress popup/completer interference during programmatic text updates
        self._programmatic_update = False
        
        # Cache line edit
        line_edit = self.lineEdit()
        line_edit.setPlaceholderText("Select tags...")
        
        # Disable built-in completer - it auto-selects first item on text change
        self.setCompleter(None)
        
        # Prevent QComboBox from writing item text into the line edit when
        # the current index changes due to model updates
        self.setInsertPolicy(QComboBox.NoInsert)
        
        # Set up the source model explicitly
        self.source_model = QStandardItemModel()
        self.setModel(self.source_model)
        
        # Keep current index at -1 so no item is ever "selected"
        self.setCurrentIndex(-1)
        
        # Set item delegate
        self.setItemDelegate(QStyledItemDelegate())
        self.tagDeleted = None

        # Use a QListView so we can intercept clicks
        view = ComboListView(self)
        view.setFocusPolicy(Qt.NoFocus)  # prevent the popup from stealing focus
        self.setView(view)

        # Connect dataChanged to updateText
        self.source_model.dataChanged.connect(lambda *_: self.updateText())
        # Re-assert index -1 whenever rows are added so nothing auto-selects
        self.source_model.rowsInserted.connect(lambda *_: self._reset_index())

        # Connect return press to addNewTagIfTyped
        line_edit.returnPressed.connect(self.onReturnPressed)

        # Event filter on the line edit to handle Tab key like Enter
        line_edit.installEventFilter(self)

    def showPopup(self) -> None:
        """
        Show the dropdown popup only when explicitly requested by a user click.

        Overrides the base implementation to block all automatic popup
        invocations (e.g. from model changes, focus events, or programmatic
        text updates). The popup is only shown when _popup_allowed is True,
        which is set exclusively in mousePressEvent.

        Returns:
            None
        """
        if not self._popup_allowed:
            return
        super().showPopup()

    def mousePressEvent(self, event) -> None:
        """
        Handle mouse press on the combo box widget.

        Sets the popup-allowed flag so that the click on the widget
        or its drop-down arrow opens the popup, then immediately
        clears it after the base class handles the event.

        Args:
            event (Any): The mouse press event.

        Returns:
            None
        """
        self._popup_allowed = True
        super().mousePressEvent(event)
        self._popup_allowed = False

    def _reset_index(self) -> None:
        """
        Reset the current index to -1 after model row insertions.

        Prevents QComboBox from auto-selecting and displaying the text of
        newly added items in the line edit.

        Returns:
            None
        """
        self._programmatic_update = True
        try:
            self.setCurrentIndex(-1)
        finally:
            self._programmatic_update = False

    def onReturnPressed(self) -> None:
        """
        Handle the return key press in the line edit.

        If the popup is open and an item is highlighted, check/uncheck that item.
        Otherwise add any newly typed tags and update the displayed text.

        Returns:
            None
        """
        if self.view().isVisible():
            idx = self.view().currentIndex()
            if idx.isValid():
                self.handleItemPressed(idx)
                self.filterItems("")   # reset filter so all items are visible next time
                self.hidePopup()
                self.updateText()
                return
        self.addNewTagIfTyped()
        self.updateText()

    def filterItems(self, query: str) -> None:
        """
        Show only items whose text contains the query string (case-insensitive).

        Passing an empty string restores all items.

        Args:
            query (str): The substring to filter by.

        Returns:
            None
        """
        lower = query.lower()
        for i in range(self.source_model.rowCount()):
            item = self.source_model.item(i, 0)
            if item:
                hidden = bool(lower) and (lower not in item.text().lower())
                self.view().setRowHidden(i, hidden)

    def forceShowPopup(self) -> None:
        """
        Show the dropdown popup regardless of the _popup_allowed guard.

        Used by external filtering code to open the popup after updating
        visible rows without requiring a mouse click. Focus is explicitly
        returned to the line edit so typing is uninterrupted.

        Returns:
            None
        """
        self._popup_allowed = True
        try:
            super().showPopup()
        finally:
            self._popup_allowed = False
        # Popup may briefly grab focus; give it straight back to the line edit
        self.lineEdit().setFocus()

    def eventFilter(self, obj, event) -> bool:
        """
        Handle keyboard events on the line edit.

        When the popup is visible, Tab behaves like Enter: it checks the
        highlighted item, resets the filter, closes the popup, and updates
        the display text.

        When the popup is closed, Tab is forwarded to Qt's normal focus chain
        explicitly via focusNextPrevChild, because QComboBox's internal event
        filter on the line edit otherwise consumes the key before focus
        navigation can act on it.

        Args:
            obj (QObject): The object that received the event.
            event (QEvent): The event.

        Returns:
            bool: True if the event was consumed, False otherwise.
        """
        if obj is self.lineEdit() and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Tab:
                if self.view().isVisible():
                    idx = self.view().currentIndex()
                    if idx.isValid():
                        self.handleItemPressed(idx)
                        self.filterItems("")
                        self.hidePopup()
                        self.updateText()
                        return True
                # Popup closed - explicitly advance focus so QComboBox's
                # internal event filter doesn't eat the Tab keystroke.
                self.focusNextPrevChild(True)
                return True
            if event.key() == Qt.Key_Backtab:
                self.focusNextPrevChild(False)
                return True
        return super().eventFilter(obj, event)

    def _on_text_changed(self, text: str) -> None:
        """
        Handle text changes in the line edit.

        Ignored during programmatic updates. No popup logic is handled
        here - popup is exclusively controlled via mousePressEvent.

        Args:
            text (str): The current text in the line edit.

        Returns:
            None
        """
        pass  # All popup control is in showPopup / mousePressEvent

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
        # Add to the source model directly (since proxy is read-only)
        item = QStandardItem(text)
        item.setData(data, Qt.UserRole)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.source_model.appendRow(item)

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
        item = self.source_model.itemFromIndex(index)
        if item:
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def checkedItems(self) -> list:
        """
        Retrieve the texts of all checked items from the source model.

        Returns:
            list: A list of checked item texts.
        """
        checked = []
        for i in range(self.source_model.rowCount()):
            item = self.source_model.item(i, 0)
            if item and item.checkState() == Qt.Checked:
                checked.append(item.text())
        return checked

    def setCheckedItems(self, items) -> None:
        """
        Set the checked state of items based on a list of strings.

        Args:
            items (list): A list of item texts to mark as checked.

        Returns:
            None
        """
        items_set = set(i.lower() for i in items)
        for i in range(self.source_model.rowCount()):
            item = self.source_model.item(i, 0)
            if item:
                item.setCheckState(
                    Qt.Checked if item.text().lower() in items_set else Qt.Unchecked
                )

    def updateText(self) -> None:
        """
        Update the line edit text to reflect checked items.

        Displays no text if none are checked, a single item if only
        one is checked, or a comma-separated list if multiple are checked.
        Uses a flag to suppress the popup during programmatic updates.

        Returns:
            None
        """
        self._programmatic_update = True
        try:
            checked = self.checkedItems()
            if not checked:
                self.lineEdit().setText("")
            elif len(checked) == 1:
                self.lineEdit().setText(checked[0])
            else:
                self.lineEdit().setText(", ".join(checked))
        finally:
            self._programmatic_update = False

    def uncheckAll(self) -> None:
        """
        Uncheck all items without removing them from the list.

        Used when resetting the form to start a new snippet while
        keeping existing tags available in the dropdown.

        Returns:
            None
        """
        # Hide popup first
        self.hidePopup()
        
        # Uncheck all items
        for i in range(self.source_model.rowCount()):
            item = self.source_model.item(i, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        
        # Clear the line edit text without triggering any side effects
        self._programmatic_update = True
        try:
            self.lineEdit().setText("")
            self.setCurrentIndex(-1)
        finally:
            self._programmatic_update = False

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

        # Split, strip whitespace, and normalize to lowercase
        candidates = [t.strip().lower() for t in raw_text.split(",") if t.strip()]
        existing = {self.source_model.item(i, 0).text().lower() for i in range(self.source_model.rowCount())}

        added_any = False
        for tag in candidates:
            if tag.lower() in existing:
                # Already present; just check it
                for i in range(self.source_model.rowCount()):
                    item = self.source_model.item(i, 0)
                    if item and item.text().lower() == tag.lower():
                        item.setCheckState(Qt.Checked)
            else:
                # New tag; add and check
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
        item = self.source_model.itemFromIndex(index)
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
                self.source_model.removeRow(index.row())
                self.tagDeleteRequested.emit(tag)
                self.updateText()
