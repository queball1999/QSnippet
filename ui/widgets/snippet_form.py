import logging
import re
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QTextEdit, QGridLayout,
    QPushButton, QHBoxLayout, QComboBox, QSizePolicy,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt, QEvent, QTimer, QSize
from PySide6.QtGui import QTextCursor, QIcon
from utils.file_utils import FileUtils
from utils.keyboard_utils import extract_dynamic_placeholder_names
from .QAnimatedSwitch import QAnimatedSwitch
from .CheckableComboBox import CheckableComboBox
from .password_field import eye_icons

# Fixed-width mask shown for encrypted snippet content so the real length is never leaked
SNIPPET_MASK = "•" * 12

class SnippetForm(QWidget):
    # Signals to notify parent
    newClicked = Signal()
    saveClicked = Signal()
    deleteClicked = Signal()
    entryChanged = Signal(dict)
    cancelPressed = Signal()

    def __init__(self, mode="new", main=None, parent=None):
        """
        Initialize the SnippetForm widget.

        Sets the form mode, stores references to the main application and parent,
        defines validation patterns, and initializes UI components and styles.

        Args:
            mode (str): Form mode, either "new" or "edit".
            main (Any): Reference to the main application object.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.main = main
        self.parent = parent
        # Mode is used to keep track of what type of form we need.
        self.mode = mode # Options: new or edit
        self.special_chars_regex = r"^\W\w{1,255}$"

        # Tag list cache - avoid DB query on every snippet click
        self.tags_filled = False
        self.cached_tags = []

        self.define_text()
        self.initUI()
        self.applyStyles()

    def define_text(self):
        """
        Define instructional and tooltip text for the form.

        Initializes descriptive text, validation requirements, and tooltips
        used throughout the snippet form interface.

        Returns:
            None
        """
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
    • Paste From Clipboard - copies the text to your system clipboard and pastes it in one go.
    • Simulate Typing - simulates typing each character (useful in apps or fields that block direct clipboard pastes)."""

    def initUI(self):
        """
        Initialize and configure all user interface components.

        Creates form fields, switches, buttons, layouts, popup completion list,
        and connects relevant signals.

        Returns:
            None
        """
        # Main Layout
        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 0, 0, 0)
        
        # Header & Instructions
        self.form_title = QLabel("Snippet Details")
        self.form_title.setObjectName("FormTitle")
        self.form_title.setFont(self.main.large_font_size_bold)

        self.instructions = QLabel(self.instructions_text)
        self.instructions.setObjectName("FormInstructions")
        self.instructions.setWordWrap(True)
        self.instructions.setFont(self.main.medium_font_size)

        instruction_height = self.instructions.sizeHint().height()
        instructions_threshold = 100

        if instruction_height > instructions_threshold:
            from PySide6.QtWidgets import QScrollArea, QFrame
            scroll = QScrollArea()
            scroll.setWidget(self.instructions)
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(instruction_height, 150))
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.instructions_widget = scroll
        else:
            self.instructions.setFixedHeight(instruction_height)
            self.instructions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            self.instructions_widget = self.instructions

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
        self.new_label.setObjectName("NameLabel")
        self.new_label.setToolTip("Name or description of your snippet.")

        self.new_input = QLineEdit(text="New Snippet", clearButtonEnabled=True)
        self.new_input.setObjectName("NameInput")
        self.new_input.setPlaceholderText("New Snippet")
        self.new_input.setToolTip("Name or description of your snippet.")
        self.new_input.setMaxLength(500)
        self.label_counter = QLabel("")
        self.label_counter.setObjectName("FieldCharCounter")
        self.label_counter.hide()
        self.new_input.textChanged.connect(self.on_label_text_changed)

        self.trigger_label = QLabel("Trigger<span style='color:red'>*</span>")
        self.trigger_label.setObjectName("TriggerLabel")
        self.trigger_label.setToolTip(self.trigger_tooltip)

        self.trigger_input = QLineEdit(clearButtonEnabled=True)
        self.trigger_input.setObjectName("TriggerInput")
        self.trigger_input.setToolTip(self.trigger_tooltip)
        self.trigger_input.setPlaceholderText("/do")
        self.trigger_input.setMaxLength(255)
        self.trigger_counter = QLabel("")
        self.trigger_counter.setObjectName("FieldCharCounter")
        self.trigger_counter.hide()
        self.trigger_input.textChanged.connect(self.on_trigger_text_changed)

        self.folder_label = QLabel("Folder")
        self.folder_label.setToolTip("Folder which your snippet is organized in.")

        self.folder_input = QComboBox()
        self.folder_input.setEditable(True)
        self.folder_input.setObjectName("FolderInput")
        self.folder_input.setToolTip("Folder which your snippet is organized in.")
        self.folder_input.setInsertPolicy(QComboBox.NoInsert)
        self.folder_input.setCompleter(None)  # Disable auto-fill; we manage filtering ourselves
        self.folder_input.setPlaceholderText("Default")
        self.folder_input.setMinimumWidth(250)
        self.folder_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Debounce timer for folder search filtering
        self.folder_all_paths = []
        self.folder_search_timer = QTimer(self)
        self.folder_search_timer.setSingleShot(True)
        self.folder_search_timer.setInterval(500)  # 500 ms debounce
        self.folder_search_timer.timeout.connect(self.filter_folder_input)
        self.folder_input.lineEdit().textEdited.connect(self.on_folder_text_edited)

        self.populate_folder_input()

        self.tags_label = QLabel("Tags")
        self.tags_label.setToolTip("Comma-separated tags to help organize and search snippets.")

        self.tags_input = CheckableComboBox()
        self.tags_input.setObjectName("TagsInput")
        self.tags_input.setToolTip("Comma-separated tags to help organize and search snippets.")
        self.tags_input.setMinimumWidth(250)
        self.tags_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tags_input.tagDeleteRequested.connect(self.on_delete_tag)
        self.populate_tags_input()

        # Debounce timer for tags search filtering
        self.tags_search_timer = QTimer(self)
        self.tags_search_timer.setSingleShot(True)
        self.tags_search_timer.setInterval(500)  # 500 ms debounce
        self.tags_search_timer.timeout.connect(self.filter_tags_input)
        self.tags_input.lineEdit().textEdited.connect(self.on_tags_text_edited)

        # Snippet Input
        self.snippet_label = QLabel("Snippet<span style='color:red'>*</span>")
        self.snippet_label.setObjectName("SnippetLabel")
        self.snippet_label.setToolTip(self.snippet_tooltip)

        self.reveal_snippet_btn = QPushButton()
        self.reveal_snippet_btn.setObjectName("RevealSnippetBtn")
        self.reveal_snippet_btn.setCursor(Qt.PointingHandCursor)
        self.reveal_snippet_btn.setFlat(True)
        self.reveal_snippet_btn.setFixedSize(26, 26)
        self.icon_eye_on, self.icon_eye_off = eye_icons()
        self.reveal_snippet_btn.setIcon(self.icon_eye_on)
        self.reveal_snippet_btn.setToolTip("Show snippet")
        self.reveal_snippet_btn.clicked.connect(self.on_reveal_snippet_toggled)
        self.reveal_snippet_btn.hide()

        self.popout_btn = QPushButton()
        self.popout_btn.setObjectName("PopoutBtn")
        self.popout_btn.setToolTip("Open in pop-out editor")
        self.popout_btn.setFixedSize(26, 26)
        self.popout_btn.clicked.connect(self.open_popout)
        self.popout_dialog = None

        self.snippet_input = QTextEdit(self)
        self.snippet_input.setObjectName("SnippetInput")
        self.snippet_input.setToolTip(self.snippet_tooltip)
        self.snippet_input.setPlaceholderText("Text that appears when you type a shortcut. Type {{ to insert placeholders, or [[ for a fill-in field...")
        self.snippet_input.setFocusPolicy(Qt.StrongFocus)
        self.snippet_input.installEventFilter(self)
        self.snippet_input.setMinimumHeight(100)
        self.snippet_counter = QLabel("")
        self.snippet_counter.setObjectName("FieldCharCounter")
        self.snippet_counter.hide()
        self.enforcing_snippet_limit = False
        self.snippet_input.textChanged.connect(self.on_snippet_text_changed)

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
        # Fill list
        self.fill_intellisense_popup_list()

        # Second popup: dynamic ([[name]]) placeholder intellisense, triggered on "[["
        self.dynamic_placeholder_popup = QListWidget(self)
        self.dynamic_placeholder_popup.hide()
        self.dynamic_placeholder_popup.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.dynamic_placeholder_popup.setFocusPolicy(Qt.NoFocus)
        self.dynamic_placeholder_popup.itemActivated.connect(self.insert_dynamic_completion)
        self.dynamic_placeholder_popup.itemClicked.connect(self.insert_dynamic_completion)
        self.fill_dynamic_placeholder_popup_list()

        # Buttons
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton('New')
        self.new_btn.setObjectName("SnippetFormBtn")

        self.save_btn = QPushButton('Save')
        self.save_btn.setObjectName("SnippetFormBtn")

        self.delete_btn = QPushButton('Delete')
        self.delete_btn.setObjectName("SnippetFormBtn")

        self.cancel_btn = QPushButton('Cancel') # Maybe rename home?
        self.cancel_btn.setObjectName("SnippetFormBtn")

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
        first_row.addWidget(self.label_counter, 2, 0, 1, 1, Qt.AlignRight)
        first_row.addWidget(self.trigger_label, 0, 1, 1, 1, Qt.AlignLeft)
        first_row.addWidget(self.trigger_input, 1, 1, 1, 1)
        first_row.addWidget(self.trigger_counter, 2, 1, 1, 1, Qt.AlignRight)

        second_row = QGridLayout()
        second_row.addWidget(self.folder_label, 0, 0, 1, 1, Qt.AlignLeft)
        second_row.addWidget(self.folder_input, 1, 0, 1, 1)
        second_row.addWidget(self.tags_label, 0, 1, 1, 1, Qt.AlignLeft)
        second_row.addWidget(self.tags_input, 1, 1, 1, 1)
        # second_row.addWidget(self.style_label, 0, 2, 1, 1, Qt.AlignLeft)
        # second_row.addWidget(self.style_combo, 1, 2, 1, 1)
        

        layout.addWidget(self.form_title, 0, 0, 1, 3, Qt.AlignLeft)
        layout.addWidget(self.instructions_widget, 1, 0, 1, 3)
        layout.addWidget(self.enabled_switch, 2, 0, 1, 1, Qt.AlignLeft)
        layout.addLayout(first_row, 3, 0, 1, 3)
        layout.addLayout(second_row, 4, 0, 1, 3)
        snippet_header = QHBoxLayout()
        snippet_header.setContentsMargins(0, 0, 0, 0)
        snippet_header.addWidget(self.snippet_label, alignment=Qt.AlignVCenter)
        snippet_header.addStretch()
        snippet_header.addWidget(self.snippet_counter, alignment=Qt.AlignVCenter)
        snippet_header.addWidget(self.reveal_snippet_btn, alignment=Qt.AlignVCenter)
        snippet_header.addWidget(self.popout_btn, alignment=Qt.AlignVCenter)
        layout.addLayout(snippet_header, 5, 0, 1, 3)
        layout.addWidget(self.snippet_input, 6, 0, 1, 3)
        layout.addWidget(self.return_switch, 7, 0, 1, 1, Qt.AlignLeft)
        layout.addWidget(self.style_switch, 7, 1, 1, 1, Qt.AlignLeft)
        layout.addLayout(btn_layout, 8, 0, 1, 3)

        # Set explicit tab order!
        # This solves the skipping snippet entry issue
        self.setTabOrder(self.new_input, self.trigger_input)
        self.setTabOrder(self.trigger_input, self.folder_input)
        self.setTabOrder(self.folder_input, self.tags_input)
        self.setTabOrder(self.tags_input, self.snippet_input)
        self.setTabOrder(self.snippet_input, self.new_btn)
        self.setTabOrder(self.new_btn, self.save_btn)
        self.setTabOrder(self.save_btn, self.delete_btn)
        self.setTabOrder(self.delete_btn, self.cancel_btn)

        QTimer.singleShot(0, self.applyStyles)  # Ensure styles are applied after full initialization

    def clear_form(self):
        """
        Clear all input fields and reset form state.

        Resets text inputs, switches, unchecks all tags (keeping them
        available in dropdown), and clears stored entry identifier.

        Returns:
            None
        """
        self.folder_input.setCurrentText("Default")
        self.entry_id = None
        self.entry_is_encrypted = False
        self.original_entry = None
        self.decrypted_snippet_cache = ""
        self.snippet_revealed = False
        self.reveal_snippet_btn.hide()
        self.snippet_input.setReadOnly(False)
        self.snippet_input.setPlaceholderText(
            "Text that appears when you type a shortcut. Type {{ to insert placeholders, or [[ for a fill-in field..."
        )
        self.new_input.clear()
        self.trigger_input.clear()
        self.snippet_input.clear()
        self.enabled_switch.setChecked(False)
        self.tags_input.filterItems("")   # reset any active filter
        self.tags_input.uncheckAll()  # Uncheck all but keep items available
        self.style_switch.setChecked(False)
        self.return_switch.setChecked(False)

    def load_entry(self, entry: dict):
        """
        Populate form fields from a snippet entry dictionary.

        Loads snippet data into corresponding UI fields, including tags,
        switch states, and folder selection.

        Args:
            entry (dict): Snippet entry containing keys such as
                folder, label, trigger, snippet, enabled, paste_style, and tags.

        Returns:
            None
        """
        self.entry_id = entry.get("id")
        self.entry_is_encrypted = bool(entry.get("is_encrypted", False))
        self.new_input.setText(entry.get('label', ''))
        self.trigger_input.setText(entry.get('trigger', ''))

        self.snippet_revealed = False
        self.decrypted_snippet_cache = ""

        # Vault: decrypt if encrypted and unlocked; show placeholder if locked
        raw_snippet = entry.get('snippet', '')
        if self.entry_is_encrypted:
            try:
                from utils.vault_manager import VaultManager
                vm = VaultManager.get_instance()
                if vm.is_unlocked():
                    aad = (entry.get("vault_uuid") or "").encode()
                    self.decrypted_snippet_cache = vm.decrypt(raw_snippet, aad=aad)
                    vm.reset_activity_timer()
                    # Always default to hidden, even when the vault is unlocked
                    raw_snippet = SNIPPET_MASK
                    self.snippet_input.setReadOnly(True)
                    self.reveal_snippet_btn.setIcon(self.icon_eye_on)
                    self.reveal_snippet_btn.setToolTip("Show snippet")
                    self.reveal_snippet_btn.show()
                else:
                    raw_snippet = ""
                    self.snippet_input.setPlaceholderText(
                        "Vault locked - click the lock icon in the folder tree to unlock."
                    )
                    self.snippet_input.setReadOnly(True)
                    self.reveal_snippet_btn.hide()
            except Exception:
                raw_snippet = ""
                self.reveal_snippet_btn.hide()
        else:
            self.snippet_input.setPlaceholderText(
                "Text that appears when you type a shortcut. Type {{ to insert placeholders, or [[ for a fill-in field..."
            )
            self.snippet_input.setReadOnly(False)
            self.reveal_snippet_btn.hide()

        self.snippet_input.setPlainText(raw_snippet)
        self.enabled_switch.setChecked(entry.get('enabled', True))
        self.folder_input.setCurrentText(entry.get('folder', 'Default'))
        self.style_switch.setChecked(entry.get('paste_style', 'Clipboard') == 'Clipboard')
        self.return_switch.setChecked(entry.get('return_press', False))

        # Tags
        self.populate_tags_input()  # load all tags
        self.tags_input.filterItems("")   # reset any active filter

        # Set all snippet tags as checked
        raw_tags = entry.get('tags', '')
        tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
        self.tags_input.setCheckedItems(tags)

        # Snapshot the loaded state so we can detect changes later
        self.original_entry = self.get_entry()

    def has_unsaved_changes(self) -> bool:
        """Return True if the form differs from its state when it was last loaded or cleared."""
        entry_id = getattr(self, "entry_id", None)

        if entry_id is None:
            name = self.new_input.text().strip()
            trigger = self.trigger_input.text().strip()
            snippet = self.snippet_input.toPlainText().strip()
            return not (name in ("", "New Snippet") and not trigger and not snippet)

        if self.original_entry is None:
            return False

        def sorted_tags(tags_str):
            return ",".join(sorted(t.strip() for t in tags_str.split(",") if t.strip()))

        current = self.get_entry()
        return (
            current["label"] != self.original_entry["label"]
            or current["trigger"] != self.original_entry["trigger"]
            or current["snippet"] != self.original_entry["snippet"]
            or current["enabled"] != self.original_entry["enabled"]
            or current["folder"] != self.original_entry["folder"]
            or current["paste_style"] != self.original_entry["paste_style"]
            or current["return_press"] != self.original_entry["return_press"]
            or sorted_tags(current["tags"]) != sorted_tags(self.original_entry["tags"])
        )

    def get_entry(self) -> dict:
        """
        Collect form data into a snippet entry dictionary.

        Reads current UI field values and formats them into a dictionary
        suitable for database insertion or update.

        Returns:
            dict: Dictionary containing snippet data.
        """
        id = getattr(self, "entry_id", None)
        folder = self.folder_input.currentText().strip() or 'Default'
        label = self.new_input.text().strip()
        trigger = self.trigger_input.text().strip()

        # If the snippet is currently masked, the real plaintext lives in the
        # cache, not in the (mask-filled) text box.
        if getattr(self, "entry_is_encrypted", False) and not getattr(self, "snippet_revealed", False):
            snippet = self.decrypted_snippet_cache
        else:
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
        """
        Populate the folder selection input from the database.

        Retrieves all folder paths (including nested), generates all intermediate
        parent paths so users can select any level, deduplicates, sorts, and loads
        them into the combo box. Caches the full list for debounce-filtered searching.

        Returns:
            None
        """
        folders = self.main.snippet_db.get_all_folders() or []

        # Build the complete set: every stored path + every intermediate parent
        path_set: set[str] = set()
        for path in folders:
            parts = path.split("/")
            for i in range(1, len(parts) + 1):
                path_set.add("/".join(parts[:i]))

        if "Default" not in path_set:
            path_set.add("Default")

        self.folder_all_paths = sorted(path_set, key=str.lower)

        self.folder_input.blockSignals(True)
        self.folder_input.clear()
        self.folder_input.addItems(self.folder_all_paths)
        self.folder_input.setCurrentText("Default")
        self.folder_input.blockSignals(False)

    def populate_tags_input(self):
        """
        Populate the tags input from the database.

        Clears existing items and adds all available tags. Uses a cached
        list to avoid a DB query on every snippet click; the cache is
        invalidated by invalidate_caches() whenever tags may have changed.

        Returns:
            None
        """
        if not self.tags_filled:
            tags = self.main.snippet_db.get_all_tags()
            self.cached_tags = tags or []
            self.tags_filled = True
        self.tags_input.clear()
        if self.cached_tags:
            self.tags_input.addItems(self.cached_tags)

    def invalidate_caches(self):
        """
        Mark cached tag list as stale so the next populate call re-queries the DB.

        Returns:
            None
        """
        self.tags_filled = False

    def on_tags_text_edited(self, text: str):
        """
        Restart the debounce timer whenever the user edits the tags line edit.

        Args:
            text (str): Current text in the line edit (unused; the timer reads
                the live widget value when it fires).

        Returns:
            None
        """
        self.tags_search_timer.stop()
        self.tags_search_timer.start()

    def filter_tags_input(self):
        """
        Filter tag dropdown items based on the last typed segment.

        Called by the debounce timer after 200 ms of inactivity. The full line
        edit text may contain previously committed tags separated by commas
        (e.g. "code, email, gp"); only the segment after the last comma is used
        as the filter query. Hides non-matching rows and opens the popup so the
        user can navigate and select with Enter or Tab.

        Returns:
            None
        """
        full_text = self.tags_input.lineEdit().text()
        # Extract last segment after the last comma as the active search term
        if "," in full_text:
            query = full_text.rsplit(",", 1)[-1].strip()
        else:
            query = full_text.strip()

        self.tags_input.filterItems(query)
        if query:
            self.tags_input.forceShowPopup()
        else:
            self.tags_input.hidePopup()

    def on_folder_text_edited(self, text: str):
        """
        Restart the debounce timer whenever the user edits the folder line edit.

        Args:
            text (str): Current text in the line edit (unused; the timer reads
                the live widget value when it fires).

        Returns:
            None
        """
        self.folder_search_timer.stop()
        self.folder_search_timer.start()

    def filter_folder_input(self):
        """
        Filter folder dropdown items based on the current search text.

        Called by the debounce timer after 200 ms of inactivity. Rebuilds the
        combo item list to show only paths that contain the typed query
        (case-insensitive), preserving the typed text in the line edit so the
        user can still save a brand-new nested path.

        Returns:
            None
        """
        query = self.folder_input.lineEdit().text()
        lower_query = query.lower()

        if lower_query:
            matching = [p for p in self.folder_all_paths if lower_query in p.lower()]
        else:
            matching = list(self.folder_all_paths)

        self.folder_input.blockSignals(True)
        self.folder_input.clear()
        self.folder_input.addItems(matching)
        self.folder_input.lineEdit().setText(query)
        self.folder_input.blockSignals(False)

        # Show dropdown so the user can navigate the filtered list
        if matching and query:
            self.folder_input.showPopup()
        else:
            self.folder_input.hidePopup()

    def on_delete_tag(self, tag):
        """
        Delete a tag from the database and refresh the UI.

        Removes the specified tag from all snippets and updates the tag input.
        Displays a confirmation message to the user.

        Args:
            tag (str): The tag name to delete.

        Returns:
            None
        """
        self.main.snippet_db.delete_tag(tag)
        self.main.message_box.info(f"Tag '{tag}' deleted from all snippets.", title="Tag Deleted")
        self.parent.load_config()   # refresh table
        self.populate_tags_input()

    def validate(self) -> bool:
        """
        Validate that all required form fields are properly filled.

        Checks that trigger, snippet, and label fields are non-empty and that
        the trigger meets the special character requirements.

        Returns:
            bool: True if validation passes, False otherwise.
        """
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
    
    # ----- Character Limit Enforcement -----
    def update_char_counter(self, counter_label: QLabel, text_len: int, max_len: int) -> None:
        """Show a live character counter when content is within 20% of its limit."""
        if text_len >= int(max_len * 0.8):
            counter_label.setText(f"{text_len:,} / {max_len:,}")
            # Colour comes from the palette, not a literal, so the counter
            # stays readable on every theme.
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.get_instance()
            colors = tm.get_colors() if tm else {}
            over = text_len >= max_len
            counter_label.setStyleSheet(
                f"color: {colors.get('danger', '#fc4f4f') if over else colors.get('warning', '#ffc107')};"
            )
            counter_label.show()
        else:
            counter_label.hide()

    def on_label_text_changed(self, text: str) -> None:
        self.update_char_counter(self.label_counter, len(text), 500)
        if len(text) >= 500:
            try:
                self.main.statusBar().showMessage("Name has reached the 500 character limit.", 3000)
            except Exception:
                pass

    def on_trigger_text_changed(self, text: str) -> None:
        self.update_char_counter(self.trigger_counter, len(text), 255)
        if len(text) >= 255:
            try:
                self.main.statusBar().showMessage("Trigger has reached the 255 character limit.", 3000)
            except Exception:
                pass

    def on_snippet_text_changed(self) -> None:
        if self.enforcing_snippet_limit:
            return
        text = self.snippet_input.toPlainText()
        length = len(text)
        max_len = 1_000_000
        if length > max_len:
            self.enforcing_snippet_limit = True
            cursor = self.snippet_input.textCursor()
            pos = cursor.position()
            self.snippet_input.setPlainText(text[:max_len])
            cursor.setPosition(min(pos, max_len))
            self.snippet_input.setTextCursor(cursor)
            self.enforcing_snippet_limit = False
            length = max_len
            try:
                self.main.statusBar().showMessage("Snippet has reached the 1,000,000 character limit.", 3000)
            except Exception:
                pass
        self.update_char_counter(self.snippet_counter, length, max_len)

    # ----- Pop-Up Menu -----
    def fill_intellisense_popup_list(self):
        """
        Populate the intellisense popup list with placeholders and snippet triggers.

        Fills the popup with available placeholder options (e.g., {date}, {time})
        and all existing snippet triggers for auto-completion.

        Returns:
            None
        """
        self.intellisense_popup.clear()

        # Fill with placeholders + sub-snippets
        self.completions = [
            "{{date}}", "{{date_long}}", "{{time}}", "{{time_ampm}}", "{{datetime}}",
            "{{weekday}}", "{{month}}", "{{year}}", "{{greeting}}", "{{location}}"
        ]

        # Add user-defined custom placeholders
        try:
            for ph in self.main.snippet_db.get_all_custom_placeholders():
                token = "{{" + ph["name"] + "}}"
                if token not in self.completions:
                    self.completions.append(token)
        except Exception:
            pass

        # Add snippet triggers too
        self.completions.extend([s["trigger"] for s in self.main.snippet_db.get_all_snippets()])
        for c in self.completions:
            QListWidgetItem(c, self.intellisense_popup)

    def show_intellisense(self):
        """
        Display the intellisense popup near the cursor position.

        Positions and shows the intellisense popup below the current cursor
        position in the snippet input field.

        Returns:
            None
        """
        if not self.isVisible():    # Exit if not visible
            return

        cursor = self.snippet_input.textCursor()
        rect = self.snippet_input.cursorRect(cursor)
        pos = self.snippet_input.mapToGlobal(rect.bottomRight())

        self.intellisense_popup.move(pos)
        self.intellisense_popup.show()
        self.snippet_input.setFocus()
        

    def insert_completion(self, item):
        """
        Insert the selected completion item at the cursor position.

        Replaces the text from the opening brace to the cursor with the
        selected completion item and hides the popup.

        Args:
            item (QListWidgetItem): The selected completion item from the popup.

        Returns:
            None
        """
        if not item:
            return
        cursor = self.snippet_input.textCursor()
        # Delete everything typed since the '{'
        start = getattr(self, "start_brace_pos", None)
        if start is not None:
            cursor.setPosition(start, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

        # Strip and format text. Placeholders (system/custom) use {{name}};
        # plain snippet triggers use {/trigger} - a nested-snippet reference,
        # which is a different, unrelated single-brace syntax.
        raw = item.text()
        formatted = raw.strip("{}")
        if raw.startswith("{"):
            completion = f"{{{{{formatted}}}}}"
        else:
            completion = f"{{{formatted}}}"

        # Insert the full completion
        cursor.insertText(completion)
        self.snippet_input.setTextCursor(cursor)
        self.intellisense_popup.hide()
        self.snippet_input.setFocus()

    def update_prefix(self):
        """
        Update the intellisense popup based on current cursor position.

        Opens on "{{" (not a single "{") so old placeholders/triggers only
        pop up once the user commits to the double-brace syntax. Recomputes
        the prefix from the nearest preceding "{{" and filters the popup
        items accordingly; hides the popup once a closing "}" or newline
        appears between that "{{" and the cursor.

        Returns:
            None
        """
        if not self.snippet_input.isVisible():  # Exit if snippet input is not visible
            return

        cursor = self.snippet_input.textCursor()
        current_text = self.snippet_input.toPlainText()
        pos = cursor.position()

        # Look backwards for the nearest opening "{{"
        start = current_text.rfind("{{", 0, pos)
        if start != -1:
            segment = current_text[start:pos]
            if "}" not in segment and "\n" not in segment:
                self.start_brace_pos = start
                self.show_intellisense()
                self.filter_intellisense(segment)
                return
        self.intellisense_popup.hide()

    def update_bracket_prefix(self):
        """
        Update the dynamic placeholder popup based on current cursor position.

        Mirrors update_prefix but for the "[[" dynamic-placeholder trigger:
        opens on "[[", recomputes the prefix from the nearest preceding "[[",
        and hides once a closing "]" or newline appears before the cursor.

        Returns:
            None
        """
        if not self.snippet_input.isVisible():
            return

        cursor = self.snippet_input.textCursor()
        current_text = self.snippet_input.toPlainText()
        pos = cursor.position()

        start = current_text.rfind("[[", 0, pos)
        if start != -1:
            segment = current_text[start:pos]
            if "]" not in segment and "\n" not in segment:
                self.start_bracket_pos = start
                self.show_dynamic_placeholder_intellisense()
                self.filter_dynamic_placeholder_intellisense(segment)
                return
        self.dynamic_placeholder_popup.hide()


    def filter_intellisense(self, prefix: str):
        """
        Filter intellisense popup items based on the provided prefix.

        Filters the completion list to show only items that match the prefix,
        handling both placeholder syntax (with braces) and plain snippet triggers.

        Args:
            prefix (str): The prefix text to filter by.

        Returns:
            None
        """
        self.intellisense_popup.clear()

        # strip brackets to ensure we match snippets too
        raw_prefix = prefix.strip("{}")

        for c in self.completions:
            candidate = c.lower()

            if c.startswith("{"):
                # Check inside placeholder name
                if raw_prefix in candidate.strip("{}"):  # skip surrounding {{ }}
                    QListWidgetItem(c, self.intellisense_popup)
            else:
                # Plain snippet trigger
                if raw_prefix in candidate:
                    QListWidgetItem(c, self.intellisense_popup)

        if self.intellisense_popup.count() > 0:
            self.intellisense_popup.setCurrentRow(0)
        else:
            self.intellisense_popup.hide()

    # ----- Dynamic ([[name]]) placeholder intellisense -----
    def fill_dynamic_placeholder_popup_list(self):
        """
        Populate the dynamic placeholder popup with [[name]] tokens already
        used across existing snippets, so previously-used fill-in field names
        can be reused via autocomplete instead of retyped from scratch.

        Returns:
            None
        """
        self.dynamic_placeholder_popup.clear()
        names = []
        try:
            for s in self.main.snippet_db.get_all_snippets():
                if s.get("is_encrypted") or not s.get("snippet"):
                    continue
                for name in extract_dynamic_placeholder_names(s["snippet"]):
                    if name not in names:
                        names.append(name)
        except Exception:
            pass

        self.dynamic_placeholder_completions = names
        for c in names:
            QListWidgetItem(c, self.dynamic_placeholder_popup)

    def show_dynamic_placeholder_intellisense(self):
        """
        Display the dynamic placeholder popup near the cursor position.

        Returns:
            None
        """
        if not self.isVisible():
            return

        cursor = self.snippet_input.textCursor()
        rect = self.snippet_input.cursorRect(cursor)
        pos = self.snippet_input.mapToGlobal(rect.bottomRight())

        self.dynamic_placeholder_popup.move(pos)
        self.dynamic_placeholder_popup.show()
        self.snippet_input.setFocus()

    def insert_dynamic_completion(self, item):
        """
        Insert the selected dynamic placeholder name as [[name]] at the cursor.

        Args:
            item (QListWidgetItem): The selected completion item from the popup.

        Returns:
            None
        """
        if not item:
            return
        cursor = self.snippet_input.textCursor()
        start = getattr(self, "start_bracket_pos", None)
        if start is not None:
            cursor.setPosition(start, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

        name = item.text().strip("[]")
        cursor.insertText(f"[[{name}]]")
        self.snippet_input.setTextCursor(cursor)
        self.dynamic_placeholder_popup.hide()
        self.snippet_input.setFocus()

    def filter_dynamic_placeholder_intellisense(self, prefix: str):
        """
        Filter the dynamic placeholder popup items based on the provided prefix.

        Args:
            prefix (str): The prefix text to filter by (e.g. "[[na").

        Returns:
            None
        """
        self.dynamic_placeholder_popup.clear()
        raw_prefix = prefix.strip("[]").lower()

        for c in getattr(self, "dynamic_placeholder_completions", []):
            if raw_prefix in c.lower():
                QListWidgetItem(c, self.dynamic_placeholder_popup)

        if self.dynamic_placeholder_popup.count() > 0:
            self.dynamic_placeholder_popup.setCurrentRow(0)
        else:
            self.dynamic_placeholder_popup.hide()

    # ----- Styling Functions -----
    def apply_tags_font(self):
        self.tags_label.setFont(self.main.medium_font_size)
        self.tags_input.setFont(self.main.medium_font_size)
        line_edit = self.tags_input.lineEdit()
        if line_edit:
            line_edit.setFont(self.main.medium_font_size)

    def apply_folder_font(self):
            self.folder_label.setFont(self.main.medium_font_size)
            self.folder_input.setFont(self.main.medium_font_size)
            line_edit = self.folder_input.lineEdit()
            if line_edit:
                line_edit.setFont(self.main.medium_font_size)

    def applyStyles(self):
        """
        Apply all styling properties to the form and its widgets.

        Sets fonts, sizes, and stylesheets for all form components including
        labels, inputs, buttons, and switches.

        Returns:
            None
        """
        # Font Sizing
        self.form_title.setFont(self.main.large_font_size_bold)
        self.instructions.setFont(self.main.medium_font_size)
        QTimer.singleShot(0, self.apply_folder_font)
        self.new_label.setFont(self.main.medium_font_size)
        self.new_input.setFont(self.main.medium_font_size)
        QTimer.singleShot(0, self.apply_tags_font)
        self.trigger_label.setFont(self.main.medium_font_size)
        self.trigger_input.setFont(self.main.medium_font_size)
        self.snippet_label.setFont(self.main.medium_font_size)
        self.snippet_input.setFont(self.main.medium_font_size)
        self.intellisense_popup.setFont(self.main.medium_font_size)
        self.label_counter.setFont(self.main.small_font_size)
        self.trigger_counter.setFont(self.main.small_font_size)
        self.snippet_counter.setFont(self.main.small_font_size)
        
        self.new_btn.setFont(self.main.medium_font_size)
        self.save_btn.setFont(self.main.medium_font_size)
        self.delete_btn.setFont(self.main.medium_font_size)
        self.cancel_btn.setFont(self.main.medium_font_size)

        # Widget Styling
        self.enabled_switch.text_font = self.main.medium_font_size
        self.enabled_switch.toggle_size = self.main.small_toggle_size
        self.enabled_switch.applyStyles()

        self.return_switch.text_font = self.main.medium_font_size
        self.return_switch.toggle_size = self.main.small_toggle_size
        self.return_switch.applyStyles()

        self.style_switch.text_font = self.main.medium_font_size
        self.style_switch.toggle_size = self.main.small_toggle_size
        self.style_switch.applyStyles()

        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.get_instance()
            icon = QIcon(FileUtils.icon_path("new-window.svg"))
            if tm:
                icon = tm.recolor_icon(icon, tm.icon_color())
            self.popout_btn.setIcon(icon)
            self.popout_btn.setIconSize(QSize(14, 14))

            # Re-render the reveal icons in the new theme's icon colour
            self.icon_eye_on, self.icon_eye_off = eye_icons()
            self.reveal_snippet_btn.setIcon(
                self.icon_eye_off if getattr(self, "snippet_revealed", False) else self.icon_eye_on
            )
            self.reveal_snippet_btn.setIconSize(QSize(14, 14))
        except Exception:
            pass

        self.layout().invalidate()
        self.update()

    def on_reveal_snippet_toggled(self) -> None:
        """Toggle the masked/plaintext display of an encrypted snippet's content."""
        self.snippet_revealed = not self.snippet_revealed
        if self.snippet_revealed:
            self.snippet_input.setPlainText(self.decrypted_snippet_cache)
            self.snippet_input.setReadOnly(False)
            self.snippet_input.setPlaceholderText(
                "Text that appears when you type a shortcut. Type {{ to insert placeholders, or [[ for a fill-in field..."
            )
            self.reveal_snippet_btn.setIcon(self.icon_eye_off)
            self.reveal_snippet_btn.setToolTip("Hide snippet")
        else:
            # Preserve any edits made while the snippet was revealed
            self.decrypted_snippet_cache = self.snippet_input.toPlainText()
            self.snippet_input.setPlainText(SNIPPET_MASK)
            self.snippet_input.setReadOnly(True)
            self.reveal_snippet_btn.setIcon(self.icon_eye_on)
            self.reveal_snippet_btn.setToolTip("Show snippet")

    # ----- Popout Editor -----
    def open_popout(self) -> None:
        if self.popout_dialog and not self.popout_dialog.isHidden():
            self.popout_dialog.raise_()
            self.popout_dialog.activateWindow()
            return
        if self.entry_is_encrypted and not self.snippet_revealed:
            self.on_reveal_snippet_toggled()
        from .snippet_popout_dialog import SnippetPopoutDialog
        self.popout_dialog = SnippetPopoutDialog(
            snippet_text=self.snippet_input.toPlainText(),
            snippet_name=self.new_input.text().strip(),
            parent=self.window()
        )
        self.popout_dialog.snippetApplied.connect(self.on_popout_applied)
        self.popout_dialog.show()

    def on_popout_applied(self, text: str) -> None:
        self.snippet_input.setPlainText(text)

    # ----- Event Handlers -----
    def eventFilter(self, obj, event):
        """
        Handle keyboard events in the snippet input field.

        Processes special key events including brace detection, popup navigation,
        and completion insertion. Shows and filters the intellisense popup based
        on user input.

        Args:
            obj (QObject): The object that received the event.
            event (QEvent): The event object.

        Returns:
            bool: True if the event was handled, False otherwise.
        """
        if obj is self.snippet_input and event.type() == QEvent.KeyPress:
            # "{{" opens the placeholder/trigger popup; "[[" opens the dynamic
            # placeholder popup. Both are deferred via update_*_prefix so the
            # just-typed character is already in the text when we scan for
            # the "{{"/"[[" pair - a single "{" or "[" alone no longer pops
            # anything up.
            if event.text() == "{":
                QTimer.singleShot(0, self.update_prefix)
                return False
            elif event.text() == "}":
                self.intellisense_popup.hide()
            elif event.text() == "[":
                QTimer.singleShot(0, self.update_bracket_prefix)
                return False
            elif event.text() == "]":
                self.dynamic_placeholder_popup.hide()

            active_popup = None
            if self.intellisense_popup.isVisible():
                active_popup = self.intellisense_popup
                active_insert = self.insert_completion
                active_update = self.update_prefix
                active_start_attr = "start_brace_pos"
            elif self.dynamic_placeholder_popup.isVisible():
                active_popup = self.dynamic_placeholder_popup
                active_insert = self.insert_dynamic_completion
                active_update = self.update_bracket_prefix
                active_start_attr = "start_bracket_pos"

            if active_popup is not None:
                # Only treat these as popup-navigation keys when pressed
                # unmodified - e.g. Shift+Right/Up/Down are text-selection
                # shortcuts and must reach the editor, not be swallowed here.
                no_modifiers = event.modifiers() in (Qt.NoModifier, Qt.KeypadModifier)
                if event.key() == Qt.Key_Down and no_modifiers:
                    row = (active_popup.currentRow() + 1) % active_popup.count()
                    active_popup.setCurrentRow(row)
                    return True
                elif event.key() == Qt.Key_Up and no_modifiers:
                    row = (active_popup.currentRow() - 1) % active_popup.count()
                    active_popup.setCurrentRow(row)
                    return True
                elif event.key() in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter) and no_modifiers:
                    active_insert(active_popup.currentItem())
                    return True
                elif event.key() in (Qt.Key_Escape, Qt.Key_Right) and no_modifiers:
                    active_popup.hide()
                    return True
                elif event.key() == Qt.Key_Space and no_modifiers:
                    # Hide the popup but still insert the space into the text
                    active_popup.hide()
                    return False
                elif event.key() == Qt.Key_Backspace and no_modifiers:
                    QTimer.singleShot(0, active_update)

                    # Check if user deleted the opening bracket/brace pair
                    cursor = self.snippet_input.textCursor()
                    start = getattr(self, active_start_attr, None)
                    if start is not None and cursor.position() <= start + 1:
                        active_popup.hide()
                        return False
                else:
                    QTimer.singleShot(0, active_update)    # Recompute regardless if visible

            # Recompute on backspace so either popup can trigger again
            if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
                QTimer.singleShot(0, self.update_prefix)
                QTimer.singleShot(0, self.update_bracket_prefix)

        return super().eventFilter(obj, event)

    def showEvent(self, event):
        """
        Handle the widget show event.

        Sets focus to the name input, reloads available tags, and refreshes
        the intellisense popup list when the form becomes visible.

        Args:
            event (QShowEvent): The show event object.

        Returns:
            None
        """
        super().showEvent(event)
        # force focus when the form is shown
        self.new_input.setFocus(Qt.TabFocusReason)
        self.populate_folder_input()
        self.populate_tags_input()
        # Reload popup list. Fixing Issue #24
        self.fill_intellisense_popup_list()
        self.fill_dynamic_placeholder_popup_list()

