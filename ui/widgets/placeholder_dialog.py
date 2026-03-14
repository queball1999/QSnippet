import re
import logging

from PySide6.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QLabel,
    QLineEdit, QTextEdit, QHeaderView, QSizePolicy, QFrame,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

logger = logging.getLogger(__name__)

# System placeholders (read-only reference)
SYSTEM_PLACEHOLDERS = [
    {"name": "date",       "description": "Current date (YYYY-MM-DD)",         "value": "e.g. 2025-09-04"},
    {"name": "date_long",  "description": "Long date (Month DD, YYYY)",        "value": "e.g. September 04, 2025"},
    {"name": "time",       "description": "Current time in 24-hour format",    "value": "e.g. 14:35"},
    {"name": "time_ampm",  "description": "Current time in 12-hour format",    "value": "e.g. 02:35 PM"},
    {"name": "datetime",   "description": "Date and time combined",            "value": "e.g. 2025-09-04 14:35"},
    {"name": "weekday",    "description": "Current weekday name",              "value": "e.g. Thursday"},
    {"name": "month",      "description": "Current month name",                "value": "e.g. September"},
    {"name": "year",       "description": "Current year",                      "value": "e.g. 2025"},
    {"name": "greeting",   "description": "Context-aware greeting",            "value": "e.g. Good Afternoon"},
]

# Name validation: letters and underscores only, 1–250 characters
_NAME_REGEX = re.compile(r"^[a-zA-Z_]{1,250}$")

# System placeholder names (for conflict checking)
_SYSTEM_NAMES = {ph["name"] for ph in SYSTEM_PLACEHOLDERS}


class PlaceholderDialog(QDialog):
    """
    Dialog for managing user-defined custom placeholders.

    Shows system placeholders as read-only reference and lets users add,
    edit, or delete their own custom placeholders.
    """

    placeholders_updated = Signal()     # Emitted whenever the list changes

    def __init__(self, snippet_db, parent=None):
        """
        Initialize the PlaceholderDialog.

        Args:
            snippet_db: SnippetDB instance for CRUD operations.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.snippet_db = snippet_db
        self.selected_row_id = None    # DB id of the currently selected custom row
        self.is_system_row = False     # Whether the selected row is a system placeholder

        self.setWindowTitle("Manage Placeholders")
        self.resize(860, 560)
        self.setMinimumSize(720, 480)

        self.build_ui()
        self.load_table()

    # UI construction

    def build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Left panel
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_widget.setFixedWidth(380)

        left_title = QLabel("Placeholders")
        left_title.setObjectName("PanelTitle")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Type", "Name", "Description"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.itemSelectionChanged.connect(self.on_row_selected)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.add_btn = QPushButton("Add Placeholder")
        self.add_btn.setObjectName("AddPlaceholderBtn")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.on_add_clicked)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("DeletePlaceholderBtn")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.on_delete_clicked)

        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.table)
        left_layout.addLayout(btn_row)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Sunken)

        # Right panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.editor_title = QLabel("Select a placeholder to edit")
        self.editor_title.setObjectName("PanelTitle")

        self.system_notice = QLabel("System placeholders are read-only and cannot be modified.")
        self.system_notice.setObjectName("SystemNotice")
        self.system_notice.setWordWrap(True)
        self.system_notice.hide()

        # Name field
        name_label = QLabel("Name")
        name_label.setObjectName("FieldLabel")
        self.name_hint = QLabel("Letters and underscores only · max 250 characters · no numbers or special characters")
        self.name_hint.setObjectName("FieldHint")
        self.name_hint.setWordWrap(True)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("my_placeholder")
        self.name_input.setMaxLength(250)
        self.name_input.textChanged.connect(self.validate_name)

        # Name validation feedback
        self.name_error = QLabel("")
        self.name_error.setObjectName("ErrorLabel")
        self.name_error.hide()

        # Description field
        desc_label = QLabel("Description")
        desc_label.setObjectName("FieldLabel")
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Short description (optional)")
        self.desc_input.setMaxLength(500)

        # Value field
        value_label = QLabel("Replacement Value")
        value_label.setObjectName("FieldLabel")
        self.value_input = QTextEdit()
        self.value_input.setPlaceholderText("Text that will replace {placeholder} when a snippet is expanded...")
        self.value_input.setAcceptRichText(False)
        self.value_input.setMinimumHeight(100)

        # Close Button
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        # Save button
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Placeholder")
        self.save_btn.setObjectName("SavePlaceholderBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.on_save_clicked)
        save_row.addStretch()
        save_row.addWidget(self.close_btn)  # Add close button
        save_row.addWidget(self.save_btn)

        right_layout.addWidget(self.editor_title)
        right_layout.addWidget(self.system_notice)
        right_layout.addWidget(name_label)
        right_layout.addWidget(self.name_hint)
        right_layout.addWidget(self.name_input)
        right_layout.addWidget(self.name_error)
        right_layout.addWidget(desc_label)
        right_layout.addWidget(self.desc_input)
        right_layout.addWidget(value_label)
        right_layout.addWidget(self.value_input)
        right_layout.addStretch()
        right_layout.addLayout(save_row)

        # Assemble
        root.addWidget(left_widget)
        root.addWidget(divider)
        root.addWidget(right_widget, 1)

        self.set_editor_enabled(False)
        self.apply_styles()

    def set_value_placeholder_hint(self, placeholder_name: str | None = None):
        """Set context-aware hint text for the replacement value field."""
        token = f"{{{placeholder_name}}}" if placeholder_name else "{placeholder}"
        self.value_input.setPlaceholderText(
            f"Text that will replace {token} when a snippet is expanded..."
        )

    def apply_styles(self):
        self.setStyleSheet("""
            QLabel#PanelTitle {
                font-size: 14px;
                font-weight: bold;
                padding-bottom: 4px;
            }
            QLabel#FieldLabel {
                font-weight: bold;
                font-size: 12px;
            }
            QLabel#FieldHint {
                font-size: 11px;
                color: #666;
            }
            QLabel#ErrorLabel {
                font-size: 11px;
                color: #e81123;
            }
            QLabel#SystemNotice {
                font-size: 11px;
                color: #5a5a5a;
                background: #f0f0f0;
                border-radius: 4px;
                padding: 6px;
            }
        """)

    # Data loading

    def load_table(self):
        """Rebuild the table from system constants + DB custom placeholders."""
        self.table.setRowCount(0)

        # System rows (read-only)
        for ph in SYSTEM_PLACEHOLDERS:
            self.add_table_row("System", ph["name"], ph["description"], row_id=None, is_system=True)

        # Custom rows from DB
        for ph in self.snippet_db.get_all_custom_placeholders():
            self.add_table_row("Custom", ph["name"], ph["description"], row_id=ph["id"], is_system=False)

    def add_table_row(self, row_type: str, name: str, description: str, row_id, is_system: bool):
        row = self.table.rowCount()
        self.table.insertRow(row)

        type_item  = QTableWidgetItem(row_type)
        name_item  = QTableWidgetItem(name)
        desc_item  = QTableWidgetItem(description)

        # Store metadata in the name cell
        name_item.setData(Qt.UserRole, {"id": row_id, "is_system": is_system})

        if is_system:
            grey = QColor("#aaaaaa")
            italic_font = QFont()
            italic_font.setItalic(True)
            for item in (type_item, name_item, desc_item):
                item.setForeground(grey)
                item.setFont(italic_font)

        for col, item in enumerate((type_item, name_item, desc_item)):
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, col, item)

    # Selection handling

    def on_row_selected(self):
        rows = self.table.selectedItems()
        if not rows:
            self.clear_editor()
            self.set_editor_enabled(False)
            self.delete_btn.setEnabled(False)
            return

        # Name cell (column 1) holds the metadata
        name_item = self.table.item(self.table.currentRow(), 1)
        meta = name_item.data(Qt.UserRole) if name_item else None
        if not meta:
            return

        self.is_system_row = meta["is_system"]
        self.selected_row_id = meta["id"]

        name = name_item.text()
        desc_item = self.table.item(self.table.currentRow(), 2)
        desc = desc_item.text() if desc_item else ""

        if self.is_system_row:
            # Show system placeholder info (read-only)
            ph = next((p for p in SYSTEM_PLACEHOLDERS if p["name"] == name), None)
            value_preview = ph["value"] if ph else ""
            self.editor_title.setText(f"{{{name}}}")
            self.set_value_placeholder_hint(name)
            self.system_notice.show()
            self.name_input.setText(name)
            self.desc_input.setText(desc)
            self.value_input.setPlainText(value_preview)
            self.set_editor_enabled(False, show_fields=True)
            self.delete_btn.setEnabled(False)
        else:
            # Editable custom placeholder
            ph_list = self.snippet_db.get_all_custom_placeholders()
            ph = next((p for p in ph_list if p["id"] == self.selected_row_id), None)
            value = ph["value"] if ph else ""
            self.editor_title.setText(f"{{{name}}}")
            self.set_value_placeholder_hint(name)
            self.system_notice.hide()
            self.name_input.setText(name)
            self.desc_input.setText(desc)
            self.value_input.setPlainText(value)
            self.set_editor_enabled(True)
            self.delete_btn.setEnabled(True)

    # Editor helpers

    def clear_editor(self):
        self.editor_title.setText("Select a placeholder to edit")
        self.name_input.clear()
        self.desc_input.clear()
        self.value_input.clear()
        self.set_value_placeholder_hint(None)
        self.name_error.hide()
        self.system_notice.hide()
        self.selected_row_id = None
        self.is_system_row = False

    def set_editor_enabled(self, enabled: bool, show_fields: bool = False):
        """Enable or disable the right-panel editor controls."""
        visible = enabled or show_fields
        for w in (self.name_input, self.desc_input, self.value_input):
            w.setReadOnly(not enabled)
            w.setVisible(visible)
        self.save_btn.setEnabled(enabled)
        self.save_btn.setVisible(visible)

    def validate_name(self, text: str):
        """Inline validation feedback for the name field."""
        if not text:
            self.name_error.hide()
            return
        if not _NAME_REGEX.match(text):
            self.name_error.setText("Name must contain only letters (A–Z, a–z) and underscores, up to 250 characters.")
            self.name_error.show()
        elif text in _SYSTEM_NAMES:
            self.name_error.setText("This name is reserved by a system placeholder and cannot be used.")
            self.name_error.show()
        else:
            self.name_error.hide()

    def name_is_valid(self, name: str) -> bool:
        return bool(_NAME_REGEX.match(name)) and name not in _SYSTEM_NAMES

    # Toolbar button actions

    def on_add_clicked(self):
        """Deselect any row and clear the editor to prepare for a new entry."""
        self.table.clearSelection()
        self.clear_editor()
        self.selected_row_id = None
        self.is_system_row = False
        self.system_notice.hide()
        self.editor_title.setText("New Placeholder")
        self.set_editor_enabled(True)
        self.name_input.setFocus()

    def on_delete_clicked(self):
        if self.selected_row_id is None or self.is_system_row:
            return

        name = self.name_input.text().strip()
        reply = QMessageBox.question(
            self,
            "Delete Placeholder",
            f"Delete the custom placeholder {{{name}}}?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok = self.snippet_db.delete_custom_placeholder(self.selected_row_id)
        if ok:
            self.clear_editor()
            self.set_editor_enabled(False)
            self.delete_btn.setEnabled(False)
            self.load_table()
            self.placeholders_updated.emit()
        else:
            QMessageBox.warning(self, "Error", "Failed to delete placeholder. Check the logs for details.")

    def on_save_clicked(self):
        name  = self.name_input.text().strip()
        desc  = self.desc_input.text().strip()
        value = self.value_input.toPlainText().strip()

        # Validation
        if not name:
            QMessageBox.warning(self, "Validation Error", "Name is required.")
            return
        if not self.name_is_valid(name):
            QMessageBox.warning(
                self, "Validation Error",
                "Name must contain only letters (A–Z, a–z) and underscores (no numbers or "
                "special characters), and be at most 250 characters long.\n\n"
                "System placeholder names cannot be reused."
            )
            return
        entry = {"name": name, "value": value, "description": desc}

        if self.selected_row_id is None:
            # New placeholder – check for duplicate name among customs
            existing = self.snippet_db.get_all_custom_placeholders()
            if any(p["name"] == name for p in existing):
                QMessageBox.warning(
                    self, "Duplicate Name",
                    f"A custom placeholder named {{{name}}} already exists.\n"
                    "Please choose a different name or edit the existing one."
                )
                return
            ok = self.snippet_db.insert_custom_placeholder(entry)
        else:
            # Updating existing – allow same name (owner), check others
            existing = self.snippet_db.get_all_custom_placeholders()
            conflict = any(p["name"] == name and p["id"] != self.selected_row_id for p in existing)
            if conflict:
                QMessageBox.warning(
                    self, "Duplicate Name",
                    f"Another custom placeholder named {{{name}}} already exists."
                )
                return
            entry["id"] = self.selected_row_id
            ok = self.snippet_db.update_custom_placeholder(entry)

        if ok:
            self.load_table()
            self.placeholders_updated.emit()
            # Re-select the saved row
            self.reselect_by_name(name)
        else:
            QMessageBox.warning(self, "Error", "Failed to save placeholder. Check the logs for details.")

    def reselect_by_name(self, name: str):
        """Select the table row matching the given name after a save."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == name:
                self.table.selectRow(row)
                return
