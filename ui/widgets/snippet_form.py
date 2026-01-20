import logging
import re
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QGridLayout,
    QPushButton, QHBoxLayout, QComboBox, QSizePolicy,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt, QEvent, QTimer
from PySide6.QtGui import QTextCursor
from .QAnimatedSwitch import QAnimatedSwitch
from .CheckableComboBox import CheckableComboBox

class SnippetForm(QWidget):
    # Signals to notify parent
    newClicked = Signal()
    saveClicked = Signal()
    deleteClicked = Signal()
    entryChanged = Signal(dict)
    cancelPressed = Signal()

    def __init__(self, mode="new", main=None, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        # Mode is used to keep track of what type of form we need.
        self.mode = mode # Options: new or edit
        self.special_chars_regex = r"^\W\w{1,255}$"

        self.define_text()
        self.initUI()
        self.applyStyles()

    def define_text(self):
        self.instructions_text = """Fill out the form below to add a new snippet or modify an existing one. 

Use the toggle to turn this snippet on or off without deleting it. Perfect for temporarily disabling shortcuts you don’t need right now. 

When you’re done, click Save to apply your changes, or Cancel to return to the home screen without saving."""
        
        self.trigger_requirements = """Trigger Requirements:
    • Must begin with a special character (e.g. ! @ # $ % ^ & * ( ) - + = , . / < >)  
    • Between 1 and 255 characters long  
    • No spaces or newline characters allowed"""
        self.trigger_tooltip = f"""A trigger is the shortcut you type to insert your snippet.

QSnippet requires a special character to start (so it won’t conflict with regular typing),
but otherwise make it something you’ll remember for each snippet. 

{self.trigger_requirements}"""
        
        self.snippet_tooltip = """A snippet is a brief or extended block of text that appears when you type a shortcut.

Snippets come in handy for text you enter often or for standard messages you send regularly."""

        self.return_tooltip = """After inserting your snippet, do you need to press return or enter?"""

        self.paste_style_tooltip = """QSnippet supports 2 ways to paste your snippet: 
    • Paste From Clipboard – copies the text to your system clipboard and pastes it in one go.
    • Simulate Typing – simulates typing each character (useful in apps or fields that block direct clipboard pastes)."""

    def initUI(self):
        # Main Layout
        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 0, 0, 0)
        
        # Header & Instructions
        self.form_title = QLabel("Snippet Details")
        self.form_title.setFont(self.main.large_font_size)

        self.instructions = QLabel(self.instructions_text)
        self.instructions.setWordWrap(True)
        self.instructions.setFont(self.main.small_font_size)
        self.instructions.setFixedHeight(self.instructions.sizeHint().height())
        self.instructions.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

         # Enabled Switch
        start_state = "on" if self.mode == "new" else "off" # set state based on mode
        self.enabled_switch = QAnimatedSwitch(objectName="enabled_switch",
                                           on_text="Enabled",
                                           off_text="Disabled",
                                           text_position="left",
                                           text_font=self.main.medium_font_size,
                                           toggle_size=self.main.small_toggle_size,
                                           start_state=start_state,
                                           parent=self)
        
        self.return_switch = QAnimatedSwitch(objectName="return_switch",
                                           on_text="Press Enter After Snippet",
                                           off_text="Press Enter After Snippet",
                                           text_position="left",
                                           text_font=self.main.small_font_size,
                                           toggle_size=self.main.small_toggle_size,
                                           start_state="off",
                                           parent=self)
        self.return_switch.setToolTip(self.return_tooltip)
        
        self.style_switch = QAnimatedSwitch(objectName="style_switch",
                                           on_text="Paste From Clipboard",
                                           off_text="Simulate Typing",
                                           text_position="left",
                                           text_font=self.main.small_font_size,
                                           toggle_size=self.main.small_toggle_size,
                                           start_state="on",
                                           parent=self)
        self.style_switch.setToolTip(self.paste_style_tooltip)

        # Form fields
        self.new_label = QLabel("Name<span style='color:red'>*</span>")
        self.new_label.setToolTip("Name or description of your snippet.")

        self.new_input = QLineEdit(text="New Snippet", clearButtonEnabled=True)
        self.new_input.setPlaceholderText("New Snippet")
        self.new_input.setToolTip("Name or description of your snippet.")

        self.trigger_label = QLabel("Trigger<span style='color:red'>*</span>")
        self.trigger_label.setToolTip(self.trigger_tooltip)

        self.trigger_input = QLineEdit(clearButtonEnabled=True)
        self.trigger_input.setToolTip(self.trigger_tooltip)
        self.trigger_input.setPlaceholderText("/do")

        self.folder_label = QLabel("Folder")
        self.folder_label.setToolTip("Folder which your snippet is organized in.")

        self.folder_input = QComboBox()
        self.folder_input.setEditable(True)
        self.folder_input.setToolTip("Folder which your snippet is organized in.")
        self.folder_input.setInsertPolicy(QComboBox.NoInsert)
        self.folder_input.setPlaceholderText("Default")
        self.folder_input.setMinimumWidth(250)
        self.folder_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.populate_folder_input()

        self.tags_label = QLabel("Tags")
        self.tags_label.setToolTip("Comma-separated tags to help organize and search snippets.")

        self.tags_input = CheckableComboBox()
        self.tags_input.setToolTip("Comma-separated tags to help organize and search snippets.")
        self.tags_input.setMinimumWidth(250)
        self.tags_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tags_input.tagDeleteRequested.connect(self.on_delete_tag)
        self.populate_tags_input()

        # Snippet Input
        self.snippet_label = QLabel("Snippet<span style='color:red'>*</span>")
        self.snippet_label.setToolTip(self.snippet_tooltip)

        self.snippet_input = QTextEdit(self)
        self.snippet_input.setToolTip(self.snippet_tooltip)
        self.snippet_input.setPlaceholderText("Text that appears when you type a shortcut. Type { to insert placeholders...")
        self.snippet_input.setFocusPolicy(Qt.StrongFocus)
        self.snippet_input.installEventFilter(self)

        # Popup list (looks like intellisense)
        self.intellisense_popup = QListWidget(self)
        self.intellisense_popup.hide()
        # self.intellisense_popup.setWindowFlags(Qt.Popup)
        self.intellisense_popup.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )

        self.intellisense_popup.setFocusPolicy(Qt.NoFocus)
        self.intellisense_popup.itemActivated.connect(self.insert_completion)
        self.intellisense_popup.itemClicked.connect(self.insert_completion)

        # Fill with placeholders + sub-snippets
        self.completions = [
            "{date}", "{date_long}", "{time}", "{time_ampm}", "{datetime}",
            "{weekday}", "{month}", "{year}", "{greeting}", "{location}"
        ]
        # Add snippet triggers too
        self.completions.extend([s["trigger"] for s in self.main.snippet_db.get_all_snippets()])
        for c in self.completions:
            QListWidgetItem(c, self.intellisense_popup)

        # Buttons
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton('New')
        self.new_btn.setFixedSize(self.main.small_button_size)

        self.save_btn = QPushButton('Save')
        self.save_btn.setFixedSize(self.main.small_button_size)

        self.delete_btn = QPushButton('Delete')
        self.delete_btn.setFixedSize(self.main.small_button_size)

        self.cancel_btn = QPushButton('Cancel') # Maybe rename home?
        self.cancel_btn.setFixedSize(self.main.small_button_size)

        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.cancel_btn)

        # Connect signals
        self.new_btn.pressed.connect(lambda *_: self.newClicked.emit())
        self.save_btn.pressed.connect(lambda *_: self.saveClicked.emit())
        self.delete_btn.pressed.connect(lambda *_: self.deleteClicked.emit())
        self.cancel_btn.pressed.connect(lambda *_: self.cancelPressed.emit())


        # Add Widgets to Grid
        first_row = QGridLayout()
        first_row.addWidget(self.new_label, 0, 0, 1, 1, Qt.AlignLeft)
        first_row.addWidget(self.new_input, 1, 0, 1, 1)
        first_row.addWidget(self.trigger_label, 0, 1, 1, 1, Qt.AlignLeft)
        first_row.addWidget(self.trigger_input, 1, 1, 1, 1)

        second_row = QGridLayout()
        second_row.addWidget(self.folder_label, 0, 0, 1, 1, Qt.AlignLeft)
        second_row.addWidget(self.folder_input, 1, 0, 1, 1)
        second_row.addWidget(self.tags_label, 0, 1, 1, 1, Qt.AlignLeft)
        second_row.addWidget(self.tags_input, 1, 1, 1, 1)
        # second_row.addWidget(self.style_label, 0, 2, 1, 1, Qt.AlignLeft)
        # second_row.addWidget(self.style_combo, 1, 2, 1, 1)
        

        layout.addWidget(self.form_title, 0, 0, 1, 3, Qt.AlignLeft)
        layout.addWidget(self.instructions, 1, 0, 1, 3, Qt.AlignLeft)
        layout.addWidget(self.enabled_switch, 2, 0, 1, 1, Qt.AlignLeft)
        layout.addLayout(first_row, 3, 0, 1, 3)
        layout.addLayout(second_row, 4, 0, 1, 3)
        layout.addWidget(self.snippet_label, 5, 0, 1, 3, Qt.AlignLeft)
        layout.addWidget(self.snippet_input, 6, 0, 1, 3)
        layout.addWidget(self.return_switch, 7, 0, 1, 1, Qt.AlignLeft)
        layout.addWidget(self.style_switch, 7, 1, 1, 1, Qt.AlignLeft)
        layout.addLayout(btn_layout, 8, 0, 1, 3)

    def clear_form(self):
        """ Clear all entries in the form. """
        self.folder_input.setCurrentText("Default")
        self.entry_id = None
        self.new_input.clear()
        self.trigger_input.clear()
        self.snippet_input.clear()
        self.enabled_switch.setChecked(False)
        self.tags_input.clear()
        self.style_switch.setChecked(False)
        self.return_switch.setChecked(False)

    def load_entry(self, entry: dict):
        """
        Populate form fields from snippet entry dict
        {folder, label, trigger, snippet, enabled, paste_style}
        """
        self.entry_id = entry.get("id")
        self.new_input.setText(entry.get('label', ''))
        self.trigger_input.setText(entry.get('trigger', ''))
        self.snippet_input.setPlainText(entry.get('snippet', ''))
        self.enabled_switch.setChecked(entry.get('enabled', True))
        self.folder_input.setCurrentText(entry.get('folder', 'Default'))
        self.style_switch.setChecked(entry.get('paste_style', 'Clipboard') == 'Clipboard')
        self.return_switch.setChecked(entry.get('return_press', False))

        # Tags
        self.populate_tags_input()  # load all tags

        # Set all snippet tags as checked
        raw_tags = entry.get('tags', '')
        tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        self.tags_input.setCheckedItems(tags)

    def get_entry(self) -> dict:
        """
        Read form fields into snippet entry dict
        """
        id = getattr(self, "entry_id", None)
        folder = self.folder_input.currentText().strip() or 'Default'
        label = self.new_input.text().strip()
        trigger = self.trigger_input.text().strip()
        snippet = self.snippet_input.toPlainText()
        enabled = self.enabled_switch.isChecked()

        # Tags
        tags = self.tags_input.checkedItems()
        tags_str = ','.join(tag.lower() for tag in tags)
        
        # Paste Style
        paste_style = "Clipboard" if self.style_switch.isChecked() else "Keystroke"
        return_press = self.return_switch.isChecked()

        return {
            'id': id,
            'folder': folder,
            'label': label,
            'trigger': trigger,
            'snippet': snippet,
            'enabled': bool(enabled),
            'paste_style': paste_style,
            'return_press': bool(return_press),
            'tags': tags_str
        }

    def populate_folder_input(self):
        # Populate from DB if available
        folders = self.main.snippet_db.get_all_folders()

        if folders:
            self.folder_input.addItems(folders)
        # Optionally add "Default" if not present
        if "Default" not in folders:
            self.folder_input.insertItem(0, "Default")
            self.folder_input.setCurrentText("Default")

    def populate_tags_input(self):
        tags = self.main.snippet_db.get_all_tags()
        self.tags_input.clear() # clear and repopulate
        if tags:
            self.tags_input.addItems(tags)

    def on_delete_tag(self, tag):
        self.main.snippet_db.delete_tag(tag)
        self.main.message_box.info(f"Tag '{tag}' deleted from all snippets.", title="Tag Deleted")
        self.parent.load_config()   # refresh table
        self.populate_tags_input()

    def validate(self) -> bool:
        """Ensure required fields are populated"""
        # FIXME: Needs additional logic here
        entry = self.get_entry()
        if not entry['trigger']:
            self.main.message_box.warning("Trigger is required!", title="Error")
            return False
        elif not entry['snippet']:
            self.main.message_box.warning("Snippet is required!", title="Error")
            return False
        elif not entry['label']:
            self.main.message_box.warning("Label is required!", title="Error")
            return False
        elif not re.match(self.special_chars_regex, entry['trigger']):
            self.main.message_box.warning(
                f"Your trigger did not meet the requirements.\n\n{self.trigger_requirements}",
                title="Error"
            )
            return False
        return True
    
    # ----- Pop-Up Menu -----
    def show_intellisense(self):
        """ Function to setup and show intellisense pop-up """
        if not self.isVisible():    # Exit if not visible
            return

        cursor = self.snippet_input.textCursor()
        rect = self.snippet_input.cursorRect(cursor)
        pos = self.snippet_input.mapToGlobal(rect.bottomRight())

        self.intellisense_popup.move(pos)
        self.intellisense_popup.show()
        self.snippet_input.setFocus()
        

    def insert_completion(self, item):
        """ Function to move cursor and insert completion. """
        if not item:
            return
        cursor = self.snippet_input.textCursor()
        # Delete everything typed since the '{'
        start = getattr(self, "start_brace_pos", None)
        if start is not None:
            cursor.setPosition(start, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

        # Strip and format text
        formatted = item.text().strip("{}")
        completion = f"{{{formatted}}}"

        # Insert the full completion
        cursor.insertText(completion)
        self.snippet_input.setTextCursor(cursor)
        self.intellisense_popup.hide()
        self.snippet_input.setFocus()

    def update_prefix(self):
        """ Recompute prefix from text and update popup """
        if not self.snippet_input.isVisible():  # Exit if snippet input is not visible
            return

        cursor = self.snippet_input.textCursor()
        current_text = self.snippet_input.toPlainText()
        pos = cursor.position()

        # Look backwards for last '{'
        start = current_text.rfind("{", 0, pos)
        if start != -1:
            # make sure the char before cursor is still a '{'
            if pos > 0 and current_text[pos - 1] == "{":
                self.start_brace_pos = start
                self.show_intellisense()
            prefix = current_text[start:pos]
            self.filter_intellisense(prefix)
        else:
            self.intellisense_popup.hide()


    def filter_intellisense(self, prefix: str):
        """ Filter popup items to only those starting with prefix """
        self.intellisense_popup.clear()

        # strip brackets to ensure we match snippets too
        raw_prefix = prefix.strip("{}")

        for c in self.completions:
            candidate = c.lower()

            if c.startswith("{"):
                # Check inside placeholder name
                if raw_prefix in candidate[1:-1]:  # skip surrounding { }
                    QListWidgetItem(c, self.intellisense_popup)
            else:
                # Plain snippet trigger
                if raw_prefix in candidate:
                    QListWidgetItem(c, self.intellisense_popup)

        if self.intellisense_popup.count() > 0:
            self.intellisense_popup.setCurrentRow(0)
        else:
            self.intellisense_popup.hide()

    # ----- Styling Functions -----
    def applyStyles(self):
        # Font Sizing
        self.form_title.setFont(self.main.large_font_size)
        self.instructions.setFont(self.main.small_font_size)
        self.folder_label.setFont(self.main.small_font_size)
        self.folder_input.setFont(self.main.small_font_size)
        self.new_label.setFont(self.main.small_font_size)
        self.new_input.setFont(self.main.small_font_size)
        self.tags_label.setFont(self.main.small_font_size)
        self.tags_input.setFont(self.main.small_font_size)
        self.trigger_label.setFont(self.main.small_font_size)
        self.trigger_input.setFont(self.main.small_font_size)
        self.snippet_label.setFont(self.main.small_font_size)
        self.snippet_input.setFont(self.main.small_font_size)
        self.intellisense_popup.setFont(self.main.small_font_size)
        
        self.new_btn.setFont(self.main.small_font_size)
        self.save_btn.setFont(self.main.small_font_size)
        self.delete_btn.setFont(self.main.small_font_size)
        self.cancel_btn.setFont(self.main.small_font_size)

        # Button Sizing
        self.new_btn.setFixedSize(self.main.small_button_size)
        self.save_btn.setFixedSize(self.main.small_button_size)
        self.delete_btn.setFixedSize(self.main.small_button_size)
        self.cancel_btn.setFixedSize(self.main.small_button_size)

        # Widget Styling
        self.enabled_switch.text_font = self.main.medium_font_size
        self.enabled_switch.toggle_size = self.main.small_toggle_size
        self.enabled_switch.applyStyles()

        self.return_switch.text_font = self.main.small_font_size
        self.return_switch.toggle_size = self.main.small_toggle_size
        self.return_switch.applyStyles()

        self.style_switch.text_font = self.main.small_font_size
        self.style_switch.toggle_size = self.main.small_toggle_size
        self.style_switch.applyStyles()

        # StyleSheet
        self.update_stylesheet()

        self.layout().invalidate()
        self.update()
    
    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        self.setStyleSheet("""
            QPushButton {
                padding: 8px;
            } 

            QComboBox {
                padding: 8px;
            }

            QLineEdit {
                padding: 8px;
            }
        """)
    
    # ----- Event Handlers -----
    def eventFilter(self, obj, event):
        if obj is self.snippet_input and event.type() == QEvent.KeyPress:
            """ Event handler for snippet input that detects { character """
            # Detect opening {
            if event.text() == "{":
                self.start_brace_pos = self.snippet_input.textCursor().position()
                self.show_intellisense()
                QTimer.singleShot(0, self.update_prefix)
                return False
            elif event.text() == "}":
                self.intellisense_popup.hide()

            if self.intellisense_popup.isVisible():
                if event.key() == Qt.Key_Down:
                    row = (self.intellisense_popup.currentRow() + 1) % self.intellisense_popup.count()
                    self.intellisense_popup.setCurrentRow(row)
                    return True
                elif event.key() == Qt.Key_Up:
                    row = (self.intellisense_popup.currentRow() - 1) % self.intellisense_popup.count()
                    self.intellisense_popup.setCurrentRow(row)
                    return True
                elif event.key() in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
                    self.insert_completion(self.intellisense_popup.currentItem())
                    return True
                elif event.key() in (Qt.Key_Escape, Qt.Key_Right):
                    self.intellisense_popup.hide()
                    return True
                elif event.key() == Qt.Key_Space:
                    # Hide the popup but still insert the space into the text
                    self.intellisense_popup.hide()
                    return False
                elif event.key() == Qt.Key_Backspace:
                    QTimer.singleShot(0, self.update_prefix)

                    # Check if user deleted the opening brace
                    cursor = self.snippet_input.textCursor()
                    if hasattr(self, "start_brace_pos") and cursor.position() <= self.start_brace_pos + 1:
                        self.intellisense_popup.hide()
                        return False
                else:
                    QTimer.singleShot(0, self.update_prefix)    # Recompute regarless if visible

            # Recompute on backspace so it can trigger pop-up again
            if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
                QTimer.singleShot(0, self.update_prefix)

        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        # force focus when the form is shown
        self.new_input.setFocus(Qt.TabFocusReason)
        self.populate_tags_input()

