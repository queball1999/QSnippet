import re
import logging

from PySide6.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QLabel,
    QLineEdit, QTextEdit, QHeaderView, QSizePolicy, QFrame,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon
from .QAnimatedSwitch import QAnimatedSwitch
from .password_field import eye_icons
from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)

# Fixed-width mask shown for encrypted values so the real length is never leaked
_VALUE_MASK = "•" * 12

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
        self.was_encrypted = False     # Track if placeholder was encrypted before editing
        self.decrypted_value_cache = ""  # Cached plaintext for the loaded encrypted row
        self.value_revealed = False      # Whether the masked value is currently shown in plaintext

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

        # Vault encryption toggle
        self.vault_encrypt_toggle = QAnimatedSwitch(
            objectName="vault_encrypt_toggle",
            on_text="Vault Encrypted",
            off_text="Vault Encrypted",
            text_position="left",
            toggle_size=QSize(50, 30),
            start_state="off",
            parent=self
        )
        self.vault_encrypt_toggle.stateChanged.connect(self.on_vault_encrypt_toggled)

        self.vault_encrypt_hint = QLabel("Value will be stored encrypted. Vault must be unlocked to view or edit.")
        self.vault_encrypt_hint.setObjectName("FieldHint")
        self.vault_encrypt_hint.setWordWrap(True)
        self.vault_encrypt_hint.hide()

        # Value field
        value_label = QLabel("Replacement Value")
        value_label.setObjectName("FieldLabel")

        self.reveal_value_btn = QPushButton()
        self.reveal_value_btn.setObjectName("RevealValueBtn")
        self.reveal_value_btn.setCursor(Qt.PointingHandCursor)
        self.reveal_value_btn.setFlat(True)
        self.reveal_value_btn.setFixedSize(28, 28)
        self.icon_eye_on, self.icon_eye_off = eye_icons()
        self.reveal_value_btn.setIcon(self.icon_eye_on)
        self.reveal_value_btn.setToolTip("Show value")
        self.reveal_value_btn.clicked.connect(self.on_reveal_value_toggled)
        self.reveal_value_btn.hide()

        self.unlock_vault_btn = QPushButton()
        self.unlock_vault_btn.setObjectName("UnlockVaultBtn")
        self.unlock_vault_btn.setCursor(Qt.PointingHandCursor)
        self.unlock_vault_btn.setFlat(True)
        self.unlock_vault_btn.setFixedSize(28, 28)
        self.unlock_vault_btn.setIcon(self._themed_icon("lock.svg"))
        self.unlock_vault_btn.setToolTip("Unlock vault to view or edit this value")
        self.unlock_vault_btn.clicked.connect(self.on_unlock_vault_clicked)
        self.unlock_vault_btn.hide()

        value_header_row = QHBoxLayout()
        value_header_row.setContentsMargins(0, 0, 0, 0)
        value_header_row.addWidget(value_label)
        value_header_row.addStretch()
        value_header_row.addWidget(self.unlock_vault_btn)
        value_header_row.addWidget(self.reveal_value_btn)

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
        right_layout.addWidget(self.vault_encrypt_toggle, alignment=Qt.AlignLeft)
        right_layout.addWidget(self.vault_encrypt_hint)
        right_layout.addLayout(value_header_row)
        right_layout.addWidget(self.value_input)
        right_layout.addStretch()
        right_layout.addLayout(save_row)

        # Assemble
        root.addWidget(left_widget)
        root.addWidget(divider)
        root.addWidget(right_widget, 1)

        self.set_editor_enabled(False)
        self.applyStyles()

    def _themed_icon(self, icon_name: str) -> QIcon:
        """Load an icon from assets/icons, tinted to match the current theme."""
        from ui.theme_manager import ThemeManager
        icon = QIcon(FileUtils.icon_path(icon_name))
        tm = ThemeManager.get_instance()
        if tm:
            icon = tm.recolor_icon(icon, tm.icon_color())
        return icon

    def set_value_placeholder_hint(self, placeholder_name: str | None = None):
        """Set context-aware hint text for the replacement value field."""
        token = f"{{{{{placeholder_name}}}}}" if placeholder_name else "{{placeholder}}"
        self.value_input.setPlaceholderText(
            f"Text that will replace {token} when a snippet is expanded..."
        )

    # Data loading

    def load_table(self):
        """Rebuild the table from system constants + DB custom placeholders."""
        self.table.setRowCount(0)

        # System rows (read-only)
        for ph in SYSTEM_PLACEHOLDERS:
            self.add_table_row("System", ph["name"], ph["description"], row_id=None, is_system=True, is_encrypted=False)

        # Custom rows from DB
        for ph in self.snippet_db.get_all_custom_placeholders():
            self.add_table_row("Custom", ph["name"], ph["description"], row_id=ph["id"], is_system=False, is_encrypted=ph.get("is_encrypted", False))

    def add_table_row(self, row_type: str, name: str, description: str, row_id, is_system: bool, is_encrypted: bool = False):
        row = self.table.rowCount()
        self.table.insertRow(row)

        type_item = QTableWidgetItem(row_type)

        # Add lock icon for encrypted custom placeholders
        if is_encrypted and not is_system:
            type_item.setIcon(self._themed_icon("lock.svg"))

        name_item  = QTableWidgetItem(name)
        desc_item  = QTableWidgetItem(description)

        # Store metadata in the name cell
        name_item.setData(Qt.UserRole, {"id": row_id, "is_system": is_system, "is_encrypted": is_encrypted})

        if is_system:
            from ui.theme_manager import ThemeManager
            grey = ThemeManager.qcolor("text_muted", "#aaaaaa")
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
            self.editor_title.setText(f"Placeholder: {{{{{name}}}}}")
            self.set_value_placeholder_hint(name)
            self.system_notice.show()
            self.name_input.setText(name)
            self.desc_input.setText(desc)
            self.value_input.setPlainText(value_preview)
            self.reveal_value_btn.hide()
            self.unlock_vault_btn.hide()
            self.set_editor_enabled(False, show_fields=True)
            self.delete_btn.setEnabled(False)
        else:
            # Editable custom placeholder
            ph_list = self.snippet_db.get_all_custom_placeholders()
            ph = next((p for p in ph_list if p["id"] == self.selected_row_id), None)
            is_encrypted = ph.get("is_encrypted", False) if ph else False
            self.was_encrypted = is_encrypted

            logger.debug("on_row_selected: placeholder '%s' (id=%s) is_encrypted=%s from DB",
                        name, self.selected_row_id, is_encrypted)

            self.editor_title.setText(f"Placeholder: {{{{{name}}}}}")
            self.set_value_placeholder_hint(name)
            self.system_notice.hide()
            self.name_input.setText(name)
            self.desc_input.setText(desc)

            # Handle vault encryption display
            self.vault_encrypt_toggle.stateChanged.disconnect(self.on_vault_encrypt_toggled)
            self.vault_encrypt_toggle.setChecked(is_encrypted)
            # Verify the toggle was set correctly
            if self.vault_encrypt_toggle.isChecked() != is_encrypted:
                logger.warning("Toggle state mismatch: requested=%s, actual=%s", is_encrypted, self.vault_encrypt_toggle.isChecked())
            self.vault_encrypt_toggle.stateChanged.connect(self.on_vault_encrypt_toggled)

            self.value_revealed = False
            self.decrypted_value_cache = ""

            self.set_editor_enabled(True)
            self.delete_btn.setEnabled(True)

            if is_encrypted:
                from utils.vault_manager import VaultManager
                vm = VaultManager.get_instance()
                if vm.is_unlocked():
                    self.unlock_vault_btn.hide()
                    try:
                        aad = (ph.get("vault_uuid") or "").encode() if ph else b""
                        self.decrypted_value_cache = vm.decrypt(ph["value"], aad=aad) if ph else ""
                        # Always default to hidden, even when the vault is unlocked
                        self.value_input.setPlainText(_VALUE_MASK)
                        self.value_input.setReadOnly(True)
                        self.reveal_value_btn.setIcon(self.icon_eye_on)
                        self.reveal_value_btn.setToolTip("Show value")
                        self.reveal_value_btn.show()
                    except Exception as e:
                        logger.warning("Failed to decrypt placeholder '%s': %s", name, e)
                        self.value_input.setPlainText("")
                        self.value_input.setReadOnly(False)
                        self.reveal_value_btn.hide()
                else:
                    self.value_input.setPlainText("")
                    self.value_input.setPlaceholderText("Vault locked; unlock to view or edit")
                    self.value_input.setReadOnly(True)
                    self.reveal_value_btn.hide()
                    self.unlock_vault_btn.show()
            else:
                self.unlock_vault_btn.hide()
                value = ph["value"] if ph else ""
                self.value_input.setPlainText(value)
                self.value_input.setReadOnly(False)
                self.value_input.setPlaceholderText("Text that will replace {" + name + "} when a snippet is expanded...")
                self.reveal_value_btn.hide()

    # Editor helpers

    def clear_editor(self):
        self.editor_title.setText("Select a placeholder to edit")
        self.name_input.clear()
        self.desc_input.clear()
        self.value_input.clear()
        self.value_input.setReadOnly(False)
        self.value_input.setPlaceholderText("Text that will replace {placeholder} when a snippet is expanded...")
        self.set_value_placeholder_hint(None)
        self.name_error.hide()
        self.system_notice.hide()
        self.vault_encrypt_toggle.setChecked(False)
        self.vault_encrypt_hint.hide()
        self.reveal_value_btn.hide()
        self.unlock_vault_btn.hide()
        self.selected_row_id = None
        self.is_system_row = False
        self.was_encrypted = False
        self.decrypted_value_cache = ""
        self.value_revealed = False

    def set_editor_enabled(self, enabled: bool, show_fields: bool = False):
        """Enable or disable the right-panel editor controls."""
        visible = enabled or show_fields
        for w in (self.name_input, self.desc_input, self.value_input):
            w.setReadOnly(not enabled)
            w.setVisible(visible)
        self.vault_encrypt_toggle.enable(enabled)
        self.vault_encrypt_toggle.setVisible(visible)
        self.save_btn.setEnabled(enabled)
        self.save_btn.setVisible(visible)

    def on_vault_encrypt_toggled(self, state):
        """Show/hide vault encryption hint when toggle is toggled."""
        if self.vault_encrypt_toggle.isChecked():
            self.vault_encrypt_hint.show()
        else:
            self.vault_encrypt_hint.hide()

    def on_reveal_value_toggled(self):
        """Toggle the masked/plaintext display of an encrypted placeholder's value."""
        self.value_revealed = not self.value_revealed
        if self.value_revealed:
            self.value_input.setPlainText(self.decrypted_value_cache)
            self.value_input.setReadOnly(False)
            self.reveal_value_btn.setIcon(self.icon_eye_off)
            self.reveal_value_btn.setToolTip("Hide value")
        else:
            # Preserve any edits made while the value was revealed
            self.decrypted_value_cache = self.value_input.toPlainText()
            self.value_input.setPlainText(_VALUE_MASK)
            self.value_input.setReadOnly(True)
            self.reveal_value_btn.setIcon(self.icon_eye_on)
            self.reveal_value_btn.setToolTip("Show value")

    def on_unlock_vault_clicked(self):
        """Prompt the user to unlock the vault, then refresh this row's display."""
        window = self.parent()
        if not hasattr(window, "show_vault_unlock"):
            return
        name = self.name_input.text().strip()
        message = f"Unlock the vault to view {{{{{name}}}}}" if name else "Unlock the vault to view this placeholder"
        window.show_vault_unlock(message=message, on_success=self.on_row_selected)

    def validate_name(self, text: str):
        """Inline validation feedback for the name field."""
        if not text:
            self.name_error.hide()
            return
        if not _NAME_REGEX.match(text):
            self.name_error.setText("Name must contain only letters (A-Z, a-z) and underscores, up to 250 characters.")
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
            f"Delete the custom placeholder {{{{{name}}}}}?\n\nThis cannot be undone.",
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
        is_vault_encrypted = self.vault_encrypt_toggle.isChecked()

        # If the value is currently masked, the real plaintext lives in the cache,
        # not in the (mask-filled) text box.
        if self.was_encrypted and not self.value_revealed:
            value = self.decrypted_value_cache.strip()
        else:
            value = self.value_input.toPlainText().strip()

        logger.debug("on_save_clicked: name=%s, is_vault_encrypted=%s", name, is_vault_encrypted)

        # Validation
        if not name:
            QMessageBox.warning(self, "Validation Error", "Name is required.")
            return
        if not self.name_is_valid(name):
            QMessageBox.warning(
                self, "Validation Error",
                "Name must contain only letters (A-Z, a-z) and underscores (no numbers or "
                "special characters), and be at most 250 characters long.\n\n"
                "System placeholder names cannot be reused."
            )
            return

        # Check vault encryption requirements
        vault_uuid = None
        if is_vault_encrypted:
            from utils.vault_manager import VaultManager
            vm = VaultManager.get_instance()
            if not vm.is_unlocked():
                QMessageBox.warning(
                    self, "Vault Locked",
                    "Vault must be unlocked to save encrypted placeholders.\n"
                    "Please unlock the vault first."
                )
                return
            try:
                import uuid as _uuid
                vault_uuid = str(_uuid.uuid4())
                encrypted_value = vm.encrypt(value, aad=vault_uuid.encode())
                logger.info("Placeholder '%s' encrypted with vault_uuid %s", name, vault_uuid)
            except Exception as e:
                logger.exception("Failed to encrypt placeholder value")
                QMessageBox.critical(
                    self, "Encryption Error",
                    f"Failed to encrypt placeholder value: {e}"
                )
                return
            entry = {"name": name, "value": encrypted_value, "description": desc, "is_encrypted": 1, "vault_uuid": vault_uuid}
        else:
            entry = {"name": name, "value": value, "description": desc, "is_encrypted": 0, "vault_uuid": None}

        if self.selected_row_id is None:
            # New placeholder - check for duplicate name among customs
            existing = self.snippet_db.get_all_custom_placeholders()
            if any(p["name"] == name for p in existing):
                QMessageBox.warning(
                    self, "Duplicate Name",
                    f"A custom placeholder named {{{{{name}}}}} already exists.\n"
                    "Please choose a different name or edit the existing one."
                )
                return
            logger.debug("Inserting new placeholder: is_encrypted=%s", entry.get("is_encrypted"))
            ok = self.snippet_db.insert_custom_placeholder(entry)
        else:
            # Updating existing - allow same name (owner), check others
            existing = self.snippet_db.get_all_custom_placeholders()
            conflict = any(p["name"] == name and p["id"] != self.selected_row_id for p in existing)
            if conflict:
                QMessageBox.warning(
                    self, "Duplicate Name",
                    f"Another custom placeholder named {{{{{name}}}}} already exists."
                )
                return
            entry["id"] = self.selected_row_id
            logger.debug("Updating placeholder id=%s: is_encrypted=%s, vault_uuid=%s",
                        self.selected_row_id, entry.get("is_encrypted"), vault_uuid)
            ok = self.snippet_db.update_custom_placeholder(entry)

        if ok:
            logger.info("Placeholder saved successfully: %s (encrypted=%s)", name, is_vault_encrypted)
            self.load_table()
            self.placeholders_updated.emit()
            # Re-select the saved row to trigger load_editor which will set the toggle correctly
            self.reselect_by_name(name)
        else:
            logger.error("Failed to save placeholder: %s", name)
            QMessageBox.warning(self, "Error", "Failed to save placeholder. Check the logs for details.")

    def reselect_by_name(self, name: str):
        """Select the table row matching the given name after a save."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == name:
                self.table.selectRow(row)
                return

    def applyStyles(self):
        """Apply the app's scaled, role-correct fonts and re-tint theme icons."""
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_fonts(self)
        self.refresh_eye_icons()

    def refresh_eye_icons(self) -> None:
        """Re-render the reveal icons for the current theme."""
        self.icon_eye_on, self.icon_eye_off = eye_icons()
        self.reveal_value_btn.setIcon(
            self.icon_eye_off if getattr(self, "value_revealed", False) else self.icon_eye_on
        )

