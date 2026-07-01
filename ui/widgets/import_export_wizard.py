import io
import logging
import yaml
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QCheckBox, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QFrame, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from utils.file_utils import FileUtils, parse_and_validate_snippets
from .password_field import PasswordField

logger = logging.getLogger(__name__)

# ─── Marker written into encrypted export files ──────────────────────────────
EXPORT_MARKER = "qsnippet_export"
EXPORT_VERSION = 1


def classify_snippets(snippets: list[dict], db) -> list[dict]:
    """Add 'status' key to each snippet: 'New' or 'Update' based on trigger in DB."""
    for s in snippets:
        existing = db.get_snippet_by_trigger(s.get("trigger", ""))
        s["status"] = "Update" if existing else "New"
    return snippets


# ─── Inline password dialog ───────────────────────────────────────────────────

class PasswordDialog(QDialog):
    """Single-field password dialog used for export encryption and encrypted import."""

    def __init__(self, title: str, prompt: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(380)
        self.password = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(14)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("VaultDialogTitle")
        lay.addWidget(self.title_label)

        self.prompt_label = QLabel(prompt)
        self.prompt_label.setObjectName("VaultDialogDesc")
        self.prompt_label.setWordWrap(True)
        lay.addWidget(self.prompt_label)

        pw_row = QHBoxLayout()
        pw_lbl = QLabel("Password:")
        pw_lbl.setObjectName("VaultFieldLabel")
        pw_lbl.setMinimumWidth(90)
        pw_row.addWidget(pw_lbl)
        self.field = PasswordField()
        self.field.setObjectName("VaultField")
        self.field.setPlaceholderText("Vault password")
        pw_row.addWidget(self.field)
        lay.addLayout(pw_row)

        self.error_label = QLabel("")
        self.error_label.setObjectName("VaultErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        lay.addWidget(self.error_label)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SnippetFormBtn")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("VaultConfirmBtn")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.on_ok_clicked)
        btns.addWidget(self.ok_btn)
        lay.addLayout(btns)

        self.applyStyles()

    def on_ok_clicked(self):
        pw = self.field.text()
        if not pw:
            self.field.setFocus()
            return
        self.password = pw
        self.accept()

    def show_error(self, msg: str):
        self.error_label.setText(msg)
        self.error_label.show()
        self.field.clear()
        self.field.setFocus()

    def applyStyles(self):
        try:
            # PasswordDialog -> ImportExportWizard -> window -> main app
            p = self.parent()
            if p is not None:
                p = p.parent()
            main = getattr(p, "parent", None)
            if main and not callable(main) and hasattr(main, "medium_font_size"):
                mf = main.medium_font_size
                sf = main.small_font_size
                self.title_label.setFont(main.large_font_size_bold)
                self.prompt_label.setFont(sf)
                self.field.setFont(mf)
                self.error_label.setFont(sf)
                for lbl in self.findChildren(QLabel, "VaultFieldLabel"):
                    lbl.setFont(mf)
                for btn in self.findChildren(QPushButton):
                    btn.setFont(mf)
        except Exception:
            pass


# ─── Main wizard ──────────────────────────────────────────────────────────────

class ImportExportWizard(QDialog):
    """
    Dialog for importing or exporting snippets with selection control.

    Modes:
    - ``"import"``: Load YAML (plain or encrypted), show preview with New/Update
      status, select which to import.
    - ``"export"``: Load from DB, select which to export, save to YAML with
      optional full-file or per-snippet vault encryption.
    """

    def __init__(self, mode: str, snippet_db, import_path=None, parent=None, vault_manager=None):
        """
        Initialize the wizard.

        Args:
            mode (str): ``"import"`` or ``"export"``.
            snippet_db: SnippetDB instance.
            import_path (Path | None): For import mode, the YAML file to load.
            parent: Parent widget.
            vault_manager: VaultManager instance for vault operations.
        """
        super().__init__(parent)
        self.mode = mode
        self.snippet_db = snippet_db
        self.import_path = import_path
        self.vm = vault_manager
        self.snippets = []
        # True when any snippet in the current table selection has vault content
        self.has_vault_in_selection = False

        title = "Import Snippets" if mode == "import" else "Export Snippets"
        self.setWindowTitle(title)
        self.resize(900, 600)
        self.setMinimumSize(700, 400)

        self.build_ui()

        if mode == "import":
            self.load_for_import(import_path)
        else:
            self.load_for_export()

        self.applyStyles()
        logger.debug("ImportExportWizard initialized in %s mode", mode)

    # ─────────────────────────────────────────────── UI construction

    def build_ui(self) -> None:
        """Construct the dialog UI."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Title
        self.title_label = QLabel(
            "Select Snippets to Import" if self.mode == "import"
            else "Select Snippets to Export"
        )
        self.title_label.setObjectName("ImportExportTitle")
        root.addWidget(self.title_label)

        # Vault lock warning (shown when vault snippets are locked on export,
        # or when encrypted snippets detected on import)
        self.vault_warning_label = QLabel()
        self.vault_warning_label.setObjectName("VaultWarningText")
        self.vault_warning_label.setWordWrap(True)
        self.vault_warning_label.hide()
        root.addWidget(self.vault_warning_label)

        # ── Select All + count ──────────────────────────────────────
        checkbox_row = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select All")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self.on_select_all_toggled)
        checkbox_row.addWidget(self.select_all_checkbox)

        self.count_label = QLabel("0 / 0 selected")
        self.count_label.setObjectName("CountLabel")
        self.count_label.setStyleSheet("color: gray; margin-left: 12px;")
        checkbox_row.addWidget(self.count_label)
        checkbox_row.addStretch()
        root.addLayout(checkbox_row)

        # ── Vault export options (export mode only) ─────────────────
        if self.mode == "export":
            self.vault_options_frame = QFrame()
            self.vault_options_frame.setObjectName("VaultOptionsFrame")
            self.vault_options_frame.setFrameShape(QFrame.StyledPanel)
            vopt_lay = QVBoxLayout(self.vault_options_frame)
            vopt_lay.setContentsMargins(10, 8, 10, 8)
            vopt_lay.setSpacing(6)

            options_title = QLabel("Vault Export Options")
            options_title.setObjectName("VaultOptionsSectionTitle")
            vopt_lay.addWidget(options_title)

            # Option 1 - encrypt entire file (shown only when vault is configured)
            self.encrypt_export_check = QCheckBox(
                "Encrypt entire export with vault password"
            )
            self.encrypt_export_check.setToolTip(
                "The export file will be encrypted using your vault password. "
                "You will need to enter your vault password to import this file."
            )
            self.encrypt_export_check.stateChanged.connect(self.on_encrypt_export_toggled)
            vopt_lay.addWidget(self.encrypt_export_check)

            self.encrypt_export_note = QLabel(
                "  You will be prompted to enter your vault password before saving."
            )
            self.encrypt_export_note.setObjectName("VaultOptionsNote")
            self.encrypt_export_note.setWordWrap(True)
            vopt_lay.addWidget(self.encrypt_export_note)

            # Option 2 - keep vault snippets encrypted in the file
            self.keep_encrypted_check = QCheckBox(
                "Keep vault snippets encrypted in export"
            )
            self.keep_encrypted_check.setToolTip(
                "Vault snippets will be exported as encrypted blobs. "
                "The vault must be unlocked on the destination machine to import them."
            )
            self.keep_encrypted_check.stateChanged.connect(self.on_keep_encrypted_toggled)
            vopt_lay.addWidget(self.keep_encrypted_check)

            self.keep_encrypted_note = QLabel(
                "  Encrypted snippets can only be imported with the same vault unlocked."
            )
            self.keep_encrypted_note.setObjectName("VaultOptionsNote")
            self.keep_encrypted_note.setWordWrap(True)
            vopt_lay.addWidget(self.keep_encrypted_note)

            # Warning shown when vault snippets are selected but neither option is checked
            self.plaintext_warning_label = QLabel(
                "Selected vault snippets will be exported as plaintext."
            )
            self.plaintext_warning_label.setObjectName("VaultWarningText")
            self.plaintext_warning_label.setWordWrap(True)
            self.plaintext_warning_label.hide()
            vopt_lay.addWidget(self.plaintext_warning_label)

            self.vault_options_frame.hide()
            root.addWidget(self.vault_options_frame)

        # ── Snippet table ───────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        if self.mode == "import":
            columns = ["", "Label", "Trigger", "Folder", "Tags", "Status"]
            col_count = 6
        else:
            columns = ["", "Label", "Trigger", "Folder", "Tags"]
            col_count = 5

        self.table.setColumnCount(col_count)
        self.table.setHorizontalHeaderLabels(columns)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        if self.mode == "import":
            self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)

        self.table.itemChanged.connect(self.update_selection_count)
        root.addWidget(self.table)

        # ── Buttons ─────────────────────────────────────────────────
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("CancelBtn")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        action_text = "Import" if self.mode == "import" else "Export"
        self.action_button = QPushButton(action_text)
        self.action_button.setObjectName("ActionBtn")
        self.action_button.clicked.connect(self.on_confirm)
        button_layout.addWidget(self.action_button)

        root.addLayout(button_layout)

    # ─────────────────────────────────────────────── Vault option callbacks

    def on_encrypt_export_toggled(self, state: int) -> None:
        """When full-file encryption is toggled, disable the per-snippet option."""
        checked = bool(state)
        if hasattr(self, "keep_encrypted_check"):
            self.keep_encrypted_check.setEnabled(not checked)
            if checked:
                self.keep_encrypted_check.setChecked(False)
        self.refresh_plaintext_warning()

    def on_keep_encrypted_toggled(self, state: int) -> None:
        self.refresh_plaintext_warning()

    def refresh_plaintext_warning(self) -> None:
        """Show inline warning when vault snippets will be written as plaintext."""
        if not hasattr(self, "plaintext_warning_label"):
            return
        encrypt_all = (
            hasattr(self, "encrypt_export_check")
            and self.encrypt_export_check.isChecked()
        )
        keep_enc = (
            hasattr(self, "keep_encrypted_check")
            and self.keep_encrypted_check.isChecked()
        )
        show = self.has_vault_in_selection and not encrypt_all and not keep_enc
        self.plaintext_warning_label.setVisible(show)

    def update_vault_options_visibility(self) -> None:
        """Show/hide the vault options frame based on vault state and selection."""
        if self.mode != "export" or not hasattr(self, "vault_options_frame"):
            return

        vault_setup = self.vm and self.vm.is_setup(self.vault_config())
        self.has_vault_in_selection = any(
            s.get("_vault_status") == "vault" for s in self.get_selected_snippets()
        )

        show_frame = vault_setup or self.has_vault_in_selection
        self.vault_options_frame.setVisible(show_frame)

        # "Encrypt entire" only makes sense when vault is configured
        if hasattr(self, "encrypt_export_check"):
            self.encrypt_export_check.setVisible(bool(vault_setup))
            self.encrypt_export_note.setVisible(bool(vault_setup))

        # "Keep encrypted" only makes sense when vault snippets are in selection
        if hasattr(self, "keep_encrypted_check"):
            self.keep_encrypted_check.setVisible(self.has_vault_in_selection)
            self.keep_encrypted_note.setVisible(self.has_vault_in_selection)

        self.refresh_plaintext_warning()

    def vault_config(self) -> dict:
        """Return app cfg dict, falling back gracefully."""
        try:
            win = self.parent()
            cfg = getattr(getattr(win, "parent", None), "cfg", None)
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    # ─────────────────────────────────────────────── Data loading

    def load_for_export(self) -> None:
        """Load all DB snippets into the table, decrypting vault snippets when possible."""
        logger.debug("Loading snippets for export")
        all_snippets = self.snippet_db.get_all_snippets() or []

        processed = []
        has_locked = False

        for s in all_snippets:
            trigger = s.get("trigger", "")
            if trigger.startswith("__vault_") and trigger.endswith("__"):
                continue

            s = dict(s)
            if s.get("is_encrypted"):
                if self.vm and self.vm.is_unlocked():
                    try:
                        aad = (s.get("vault_uuid") or "").encode()
                        s["snippet"] = self.vm.decrypt(s["snippet"], aad=aad)
                        s["_vault_status"] = "vault"
                    except Exception:
                        s["_vault_status"] = "error"
                else:
                    s["_vault_status"] = "locked"
                    has_locked = True
            else:
                s["_vault_status"] = "normal"

            processed.append(s)

        self.snippets = processed

        if has_locked:
            self.vault_warning_label.setText(
                "Some snippets are in a locked vault and cannot be exported. "
                "Unlock the vault first to include them."
            )
            self.vault_warning_label.show()

        self.populate_table()

        # Wire selection changes to vault-option visibility after table is ready
        self.table.itemChanged.connect(self.update_vault_options_visibility)
        self.update_vault_options_visibility()

    def load_for_import(self, path: Path) -> None:
        """Load a YAML export file with full validation.

        Handles both plain exports and encrypted export bundles.  For encrypted
        files the user is prompted for their vault password before the file is
        decrypted in memory.  Per-snippet encrypted entries (``is_encrypted: true``)
        are decrypted via the current vault if it is unlocked, or skipped with a
        warning if the vault is locked.

        Args:
            path: Path to the YAML export file.
        """
        logger.debug("Loading YAML for import: %s", path)

        try:
            raw = FileUtils.read_yaml(path)
        except Exception as exc:
            logger.exception("Failed to read import file: %s", exc)
            QMessageBox.critical(self, "Import Error", f"Failed to read file:\n\n{exc}")
            self.reject()
            return

        # ── Detect and decrypt full-file encrypted bundle ──────────
        if isinstance(raw, dict) and raw.get(EXPORT_MARKER, {}).get("encrypted"):
            raw = self.decrypt_import_bundle(raw)
            if raw is None:
                self.reject()
                return

        # ── Detect per-snippet encrypted entries ────────────────────
        raw_snippets = raw.get("snippets", []) if isinstance(raw, dict) else []
        has_encrypted_snippets = any(
            isinstance(s, dict) and s.get("is_encrypted") for s in raw_snippets
        )

        if has_encrypted_snippets:
            if not (self.vm and self.vm.is_unlocked()):
                self.vault_warning_label.setText(
                    "This file contains encrypted snippets. "
                    "Unlock the vault before importing to decrypt them. "
                    "Encrypted snippets will be skipped if the vault remains locked."
                )
                self.vault_warning_label.show()

        # ── Pre-process encrypted snippets before validation ────────
        # Decrypt is_encrypted blobs in memory so they pass field validation
        # (encrypted blobs may exceed MAX_FIELD_LENGTH for normal snippets)
        decrypted_raw = self.preprocess_encrypted_snippets(raw)

        # Capture private display flags before sanitize_snippet strips them.
        # Key by (trigger, label) tuple for resilience if triggers aren't unique.
        flag_keys = ("_was_encrypted", "_decrypt_failed", "_vault_locked")
        flag_map: dict[tuple, dict] = {}
        for s in (decrypted_raw.get("snippets") or []):
            if isinstance(s, dict):
                flags = {k: s[k] for k in flag_keys if k in s}
                if flags:
                    flag_map[(s.get("trigger", ""), s.get("label", ""))] = flags

        # ── Validate and sanitize ────────────────────────────────────
        try:
            self.snippets = parse_and_validate_snippets(decrypted_raw)
            # Re-attach display flags that sanitize_snippet stripped
            for s in self.snippets:
                key = (s.get("trigger", ""), s.get("label", ""))
                s.update(flag_map.get(key, {}))
            self.snippets = classify_snippets(self.snippets, self.snippet_db)
        except (ValueError, TypeError) as exc:
            logger.exception("YAML validation failed: %s", exc)
            QMessageBox.critical(self, "Import Error", f"Invalid file:\n\n{exc}")
            self.reject()
            return
        except Exception as exc:
            logger.exception("Failed to load import file: %s", exc)
            QMessageBox.critical(self, "Import Error", f"Failed to load file:\n\n{exc}")
            self.reject()
            return

        self.populate_table()

    def decrypt_import_bundle(self, raw: dict):
        """Prompt for password and decrypt an encrypted export bundle.

        Args:
            raw: Parsed YAML dict containing the ``qsnippet_export`` header.

        Returns:
            dict | None: Decrypted and re-parsed inner YAML dict, or ``None``
                on failure / cancellation.
        """
        from utils.vault_manager import VaultManager
        header = raw.get(EXPORT_MARKER, {})

        dlg = PasswordDialog(
            title="Encrypted Import",
            prompt=(
                "This export file is encrypted.\n"
                "Enter the vault password that was used to protect it."
            ),
            parent=self,
        )

        while True:
            if dlg.exec() != QDialog.Accepted:
                return None
            try:
                decrypted_bytes = VaultManager.decrypt_export(header, dlg.password)
                inner = yaml.safe_load(io.BytesIO(decrypted_bytes))
                if not isinstance(inner, dict) or "snippets" not in inner:
                    raise ValueError("Decrypted content is not a valid snippets file.")
                logger.info("Encrypted import bundle decrypted successfully")
                return inner
            except Exception as exc:
                logger.warning("Import decryption failed: %s", exc)
                dlg.show_error("Incorrect password or corrupted file. Please try again.")

    def preprocess_encrypted_snippets(self, raw: dict) -> dict:
        """Decrypt is_encrypted snippet entries in a raw parsed YAML dict.

        Attempts to decrypt each snippet whose ``is_encrypted`` flag is ``true``
        using the current vault (if unlocked).  Failed decryptions are tagged
        with ``_decrypt_failed: True`` and their ``snippet`` field is set to an
        empty string so they pass field-length validation.

        Args:
            raw: Parsed YAML dict (may contain ``is_encrypted`` entries).

        Returns:
            dict: Copy of *raw* with encrypted blobs replaced by plaintext.
        """
        snippets = raw.get("snippets", [])
        if not snippets:
            return raw

        processed = []
        for s in snippets:
            if not (isinstance(s, dict) and s.get("is_encrypted")):
                processed.append(s)
                continue

            s = dict(s)
            s.pop("is_encrypted", None)  # strip before validation

            if self.vm and self.vm.is_unlocked():
                try:
                    aad = (s.get("vault_uuid") or "").encode()
                    s["snippet"] = self.vm.decrypt(s["snippet"], aad=aad)
                    s["_was_encrypted"] = True
                except Exception:
                    s["snippet"] = ""
                    s["_decrypt_failed"] = True
            else:
                s["snippet"] = ""
                s["_was_encrypted"] = True
                s["_vault_locked"] = True

            processed.append(s)

        return dict(raw, snippets=processed)

    # ─────────────────────────────────────────────── Table rendering

    def populate_table(self) -> None:
        """Fill the table with snippet rows and checkboxes."""
        self.table.setRowCount(len(self.snippets))

        for row_idx, snippet in enumerate(self.snippets):
            vault_status = snippet.get("_vault_status", "normal")
            is_locked_vault = vault_status == "locked"

            # Import-mode per-snippet flags
            decrypt_failed = snippet.get("_decrypt_failed", False)
            vault_locked_import = snippet.get("_vault_locked", False)
            was_encrypted = snippet.get("_was_encrypted", False)

            # Rows that can't be imported/exported are disabled
            disabled = is_locked_vault or decrypt_failed or vault_locked_import

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(not disabled)
            checkbox.setEnabled(not disabled)
            checkbox.stateChanged.connect(self.update_selection_count)
            if self.mode == "export":
                checkbox.stateChanged.connect(self.update_vault_options_visibility)
            checkbox.snippet = snippet
            self.table.setCellWidget(row_idx, 0, checkbox)

            # Label
            label_item = QTableWidgetItem(snippet.get("label", ""))
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 1, label_item)

            # Trigger
            trigger_item = QTableWidgetItem(snippet.get("trigger", ""))
            trigger_item.setFlags(trigger_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 2, trigger_item)

            # Folder - append status tag when relevant
            folder_text = snippet.get("folder", "")
            if vault_status == "vault":
                folder_text += "  [Vault]"
            elif is_locked_vault:
                folder_text += "  [Vault - Locked]"
            elif was_encrypted and not decrypt_failed and not vault_locked_import:
                folder_text += "  [Encrypted]"
            elif decrypt_failed:
                folder_text += "  [Decrypt Failed]"
            elif vault_locked_import:
                folder_text += "  [Vault Locked]"

            folder_item = QTableWidgetItem(folder_text)
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemIsEditable)
            if disabled:
                folder_item.setForeground(QColor(150, 150, 150))
            self.table.setItem(row_idx, 3, folder_item)

            # Tags
            tags_item = QTableWidgetItem(snippet.get("tags", ""))
            tags_item.setFlags(tags_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 4, tags_item)

            # Status (import only)
            if self.mode == "import":
                if disabled:
                    status_text = "Skipped"
                    status_color = QColor(150, 150, 150)
                else:
                    status_text = snippet.get("status", "Unknown")
                    status_color = (
                        QColor(100, 180, 100) if status_text == "New"
                        else QColor(200, 140, 50)
                    )
                status_item = QTableWidgetItem(status_text)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                status_item.setForeground(status_color)
                self.table.setItem(row_idx, 5, status_item)

        self.update_selection_count()

    # ─────────────────────────────────────────────── Selection helpers

    def on_select_all_toggled(self) -> None:
        """Handle Select All checkbox state change."""
        self.table.blockSignals(True)
        checked = self.select_all_checkbox.isChecked()
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb and isinstance(cb, QCheckBox) and cb.isEnabled():
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self.table.blockSignals(False)
        self.update_selection_count()
        if self.mode == "export":
            self.update_vault_options_visibility()

    def get_selected_snippets(self) -> list[dict]:
        """Return list of checked, non-disabled snippet dicts."""
        selected = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb and isinstance(cb, QCheckBox) and cb.isChecked():
                selected.append(cb.snippet)
        return selected

    def update_count_only(self) -> None:
        total = self.table.rowCount()
        selected = len(self.get_selected_snippets())
        self.count_label.setText(f"{selected} / {total} selected")
        self.action_button.setEnabled(selected > 0)

    def update_selection_count(self) -> None:
        """Update count label and sync the Select All checkbox."""
        self.update_count_only()
        if self.table.rowCount() > 0:
            self.select_all_checkbox.blockSignals(True)
            selected = len(self.get_selected_snippets())
            self.select_all_checkbox.setChecked(selected == self.table.rowCount())
            self.select_all_checkbox.blockSignals(False)

    # ─────────────────────────────────────────────── Confirm / action

    def on_confirm(self) -> None:
        """Handle Import/Export button click."""
        selected = self.get_selected_snippets()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one snippet.")
            return

        if self.mode == "import":
            self.do_import(selected)
        else:
            self.do_export(selected)

    # ─────────────────────────────────────────────── Import

    def do_import(self, snippets: list[dict]) -> None:
        """Import selected snippets into the database.

        Uses :meth:`SnippetDB.insert_snippet_vault_aware` so snippets whose
        destination folder is a vault folder are automatically encrypted.

        Args:
            snippets: List of snippet dicts to import (already decrypted).
        """
        from utils.vault_manager import VaultError

        logger.debug("Importing %d selected snippets", len(snippets))
        db_before = len(self.snippet_db.get_all_snippets() or [])

        new_count = updated_count = error_count = vault_locked_count = 0

        for entry in snippets:
            clean_entry = {
                k: v for k, v in entry.items()
                if k not in ("id", "is_encrypted") and not k.startswith("_")
            }

            try:
                result = self.snippet_db.insert_snippet_vault_aware(
                    clean_entry, vault_manager=self.vm
                )
                if result is True:
                    new_count += 1
                elif result is False:
                    updated_count += 1
                else:
                    error_count += 1
            except VaultError:
                vault_locked_count += 1
                logger.warning("Skipped vault-folder snippet (vault locked): %s",
                               entry.get("trigger"))
            except Exception as exc:
                error_count += 1
                logger.warning("Import error for %s: %s", entry.get("trigger"), exc)

        db_after = len(self.snippet_db.get_all_snippets() or [])
        logger.info(
            "Import complete: before=%d after=%d new=%d updated=%d errors=%d locked=%d",
            db_before, db_after, new_count, updated_count, error_count, vault_locked_count,
        )

        msg = f"Imported {new_count} new snippets.\nUpdated {updated_count} existing snippets."
        if vault_locked_count:
            msg += (
                f"\n\n{vault_locked_count} snippet(s) in vault folders were skipped "
                "because the vault is locked. Unlock the vault and import again to include them."
            )
        if error_count:
            msg += f"\n\n{error_count} snippet(s) could not be imported due to errors."

        QMessageBox.information(self, "Import Complete", msg)
        self.accept()

    # ─────────────────────────────────────────────── Export

    def do_export(self, snippets: list[dict]) -> None:
        """Export selected snippets, with optional vault encryption.

        Handles three export paths:
        1. Full-file AES-256-GCM encryption (vault password required)
        2. Per-snippet keep-encrypted (vault blobs preserved in plain YAML)
        3. Plain YAML (default; confirmation required if vault snippets included)

        Args:
            snippets: List of checked snippet dicts.
        """
        encrypt_all = (
            hasattr(self, "encrypt_export_check")
            and self.encrypt_export_check.isChecked()
        )
        keep_enc = (
            hasattr(self, "keep_encrypted_check")
            and self.keep_encrypted_check.isChecked()
        )
        vault_snippets = [s for s in snippets if s.get("_vault_status") == "vault"]

        # ── Confirm: vault snippets going out as plaintext ──────────
        if vault_snippets and not encrypt_all and not keep_enc:
            reply = QMessageBox.question(
                self,
                "Exporting Vault Snippets as Plaintext",
                f"{len(vault_snippets)} vault snippet(s) will be exported as plain text.\n\n"
                "The exported file will not be encrypted and anyone with access to it "
                "will be able to read these snippets.\n\n"
                "Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        # ── Prompt for vault password (full-file encryption) ────────
        export_password: str | None = None
        if encrypt_all:
            export_password = self.prompt_vault_password_for_export()
            if export_password is None:
                return  # user cancelled or entered wrong password

        # ── Choose save path ────────────────────────────────────────
        date = datetime.now().date()
        default_name = f"qsnippets-export-{date}.yaml"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Snippets",
            str(Path.home() / default_name),
            "YAML Files (*.yaml *.yml)",
        )
        if not path:
            logger.debug("Export cancelled by user")
            return

        # ── Build clean snippet list ─────────────────────────────────
        clean = []
        for s in snippets:
            row: dict = {}
            for k, v in s.items():
                if k.startswith("_") or k == "id":
                    continue
                if k == "is_encrypted":
                    continue
                row[k] = v

            if keep_enc and not encrypt_all and s.get("_vault_status") == "vault":
                # Restore the original encrypted blob from DB
                try:
                    db_row = self.snippet_db.get_snippet_by_trigger(s.get("trigger", ""))
                    if db_row and db_row.get("is_encrypted"):
                        row["snippet"] = db_row["snippet"]
                        row["is_encrypted"] = True
                        row["vault_uuid"] = db_row.get("vault_uuid")
                except Exception:
                    pass  # fall back to decrypted content already in s

            clean.append(row)

        # ── Serialise and optionally encrypt ────────────────────────
        try:
            if encrypt_all and export_password:
                self.write_encrypted_export(Path(path), clean, export_password)
            else:
                FileUtils.export_snippets_yaml(Path(path), clean)

            logger.info("Export complete: %d snippets to %s", len(clean), path)
            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(clean)} snippets." + (
                    "\n\nThe file is encrypted with your vault password." if encrypt_all else ""
                ),
            )
            self.accept()
        except Exception as exc:
            logger.exception("Export failed: %s", exc)
            QMessageBox.critical(self, "Export Error", f"Failed to export snippets:\n{exc}")

    def prompt_vault_password_for_export(self) -> str | None:
        """Show password dialog and verify against vault config.

        Returns:
            str | None: The verified password, or ``None`` on cancellation or
                repeated failure.
        """
        from utils.vault_manager import VaultManager
        cfg = self.vault_config()
        vm = VaultManager.get_instance()

        dlg = PasswordDialog(
            title="Encrypt Export",
            prompt=(
                "Enter your vault password to encrypt the export file.\n\n"
                "You will need this password when importing the file."
            ),
            parent=self,
        )

        for _ in range(3):
            if dlg.exec() != QDialog.Accepted:
                return None
            # Verify the password is correct for this vault
            if vm.is_setup(cfg):
                import base64, hmac as _hmac, hashlib
                v = cfg.get("vault", {})
                try:
                    salt = base64.b64decode(v["salt"])
                    stored = base64.b64decode(v["verifier"])
                    key = VaultManager.derive_key(dlg.password, salt)
                    if _hmac.compare_digest(VaultManager.make_verifier(key), stored):
                        return dlg.password
                    dlg.show_error("Incorrect vault password. Please try again.")
                except Exception:
                    dlg.show_error("Could not verify password. Please try again.")
            else:
                # Vault not configured; accept any non-empty password
                return dlg.password

        return None

    def write_encrypted_export(self, path: Path, snippets: list[dict], password: str) -> None:
        """Serialise *snippets* to YAML, encrypt, and write to *path*.

        The output file is a YAML document with a ``qsnippet_export`` header
        containing the KDF parameters and the AES-256-GCM ciphertext.

        Args:
            path: Destination file path.
            snippets: Clean snippet list (no internal fields).
            password: Password for AES-256-GCM encryption.
        """
        from utils.vault_manager import VaultManager

        inner_data = yaml.safe_dump({"snippets": snippets}, allow_unicode=True)
        inner_bytes = inner_data.encode("utf-8")

        header = VaultManager.encrypt_export(inner_bytes, password)
        bundle = {
            EXPORT_MARKER: {
                "version": EXPORT_VERSION,
                "encrypted": True,
                **header,
            }
        }

        FileUtils.write_yaml(path, bundle)
        logger.info("Encrypted export written to %s", path)

    # ─────────────────────────────────────────────── Styles

    def applyStyles(self) -> None:
        """Apply fonts from the main app to all widgets."""
        try:
            main_app = getattr(self.parent(), "parent", None)
            if not main_app or not hasattr(main_app, "medium_font_size"):
                return

            font = main_app.medium_font_size
            title_font = getattr(
                main_app, "large_font_size_bold",
                getattr(main_app, "large_font_size", font)
            )
            small_font = getattr(main_app, "small_font_size", font)

            self.setFont(font)
            if hasattr(self, "title_label"):
                self.title_label.setFont(title_font)
            for child in self.findChildren(QLabel):
                if child is getattr(self, "title_label", None):
                    continue
                name = child.objectName()
                if name in ("VaultOptionsNote", "VaultWarningText"):
                    child.setFont(small_font)
                elif name == "VaultOptionsSectionTitle":
                    child.setFont(getattr(main_app, "medium_font_size_bold", font))
                else:
                    child.setFont(font)
            for child in self.findChildren(QPushButton):
                child.setFont(font)
            for child in self.findChildren(QCheckBox):
                child.setFont(font)
            if hasattr(self, "table"):
                self.table.setFont(font)
                self.apply_header_font(self.table.horizontalHeader(), font)
        except Exception:
            pass

    def apply_header_font(self, header, font) -> None:
        if not header:
            return
        header.setFont(font)
        header.viewport().update()
        header.update()
