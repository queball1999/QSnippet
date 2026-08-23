import sqlite3
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QScrollArea, QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal

logger = logging.getLogger(__name__)


class DbCopyWorker(QThread):
    """Background worker that copies a SQLite DB using the backup API."""

    finished = Signal(bool, str)

    def __init__(self, src: Path, dst: Path, parent=None):
        super().__init__(parent)
        self.src = src
        self.dst = dst

    def run(self):
        try:
            self.dst.parent.mkdir(parents=True, exist_ok=True)
            src_conn = sqlite3.connect(str(self.src))
            dst_conn = sqlite3.connect(str(self.dst))
            try:
                src_conn.backup(dst_conn)
                logger.info("Database copied from %s to %s", self.src, self.dst)
            finally:
                dst_conn.close()
                src_conn.close()
            self.finished.emit(True, "")
        except Exception as exc:
            logger.exception("Database copy failed")
            self.finished.emit(False, str(exc))


class DbSettingsPage(QWidget):
    """Database storage configuration panel shown inside the main settings dialog."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.copy_worker = None
        self.pending_action = None  # Track user's choice from browse dialog
        self.build_ui()
        self.refresh_state()
        self.applyStyles()

    # ------------------------------------------------------------------
    # Helpers to read current state from the running app
    # ------------------------------------------------------------------

    @property
    def current_db_path(self) -> Path:
        """Effective DB file path currently open."""
        return Path(self.window.parent.snippet_db_file)

    @property
    def default_db_dir(self) -> Path:
        """Default app-data directory for the DB."""
        return Path(self.window.parent.app_data_dir)

    @property
    def current_setting_dir(self) -> str:
        """The directory stored in settings (empty string = use default)."""
        return (
            self.window.parent.settings
            .get("saving", {})
            .get("db_path", {})
            .get("value", "")
            or ""
        ).strip()

    def resolve_db_path(self, dir_text: str) -> Path:
        """Resolve the effective DB file path for a given directory string."""
        dir_text = (dir_text or "").strip()
        if dir_text:
            return Path(dir_text) / "snippets.db"
        return self.default_db_dir / "snippets.db"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        self.header = QLabel("Database Storage")
        self.header.setObjectName("SettingsHeader")
        layout.addWidget(self.header)

        # Body content is nested a bit further right than the header, matching
        # the extra inset dynamically generated pages get from SettingsCard's
        # own internal margin.
        content = QVBoxLayout()
        content.setContentsMargins(8, 0, 0, 0)
        content.setSpacing(12)
        layout.addLayout(content)

        # Description
        desc = QLabel(
            "Set a custom directory for the snippets database file (snippets.db).\n\n"
            "Supported locations include cloud-synced folders (NextCloud, OneDrive, Dropbox, etc.) "
            "and network shares (SMB/NFS). This allows your snippets to follow you across devices.\n\n"
            "Vault snippets are the exception: their key material lives in this device's config "
            "file rather than in the database, so a synced database cannot be unlocked on another "
            "device. Move vault content with an encrypted export and import.\n\n"
            "Leave blank to use the default app data location."
        )
        desc.setObjectName("SettingsCardDescription")
        desc.setWordWrap(True)
        content.addWidget(desc)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setObjectName("VaultSeparator")
        content.addWidget(sep1)

        # Current effective location
        current_lbl = QLabel("Current location:")
        current_lbl.setObjectName("SettingsCardTitle")
        content.addWidget(current_lbl)

        self.current_path_label = QLabel()
        self.current_path_label.setObjectName("SettingsCardDescription")
        self.current_path_label.setWordWrap(True)
        self.current_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content.addWidget(self.current_path_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setObjectName("VaultSeparator")
        content.addWidget(sep2)

        # Directory picker
        dir_lbl = QLabel("Custom database directory:")
        dir_lbl.setObjectName("SettingsCardTitle")
        content.addWidget(dir_lbl)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Leave blank to use default app data location")
        self.path_edit.textChanged.connect(self.on_path_text_changed)
        path_row.addWidget(self.path_edit, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setObjectName("SnippetFormBtn")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setToolTip("Choose a directory for the snippets database file")
        self.browse_btn.clicked.connect(self.on_browse)
        path_row.addWidget(self.browse_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("SnippetFormBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setToolTip("Clear the custom directory and use the default app data location")
        self.clear_btn.clicked.connect(self.on_clear)
        path_row.addWidget(self.clear_btn)

        content.addLayout(path_row)

        # Apply button
        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("VaultConfirmBtn")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.setToolTip("Apply the database directory change")
        self.apply_btn.clicked.connect(self.on_apply)
        btn_row.addWidget(self.apply_btn)
        btn_row.addStretch()
        content.addLayout(btn_row)

        # Inline status label
        self.status_label = QLabel()
        self.status_label.setObjectName("SettingsCardDescription")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        content.addWidget(self.status_label)

        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def refresh_state(self):
        current_db = self.current_db_path
        current_dir = self.current_setting_dir

        if current_dir:
            self.current_path_label.setText(f"{current_db}  (custom)")
        else:
            self.current_path_label.setText(f"{current_db}  (default)")

        self.path_edit.blockSignals(True)
        self.path_edit.setText(current_dir)
        self.path_edit.blockSignals(False)

        self.pending_action = None
        self.status_label.hide()

    def on_path_text_changed(self, text: str):
        self.pending_action = None
        self.status_label.hide()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_browse(self):
        start = self.path_edit.text().strip() or str(self.default_db_dir)
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Database Directory",
            start,
        )
        if directory:
            # Check if selected directory already has a database
            selected_db = Path(directory) / "snippets.db"
            if selected_db.exists():
                action = self.prompt_for_existing_db(selected_db)
                if action == "use_existing":
                    # Set the path and track the action
                    self.path_edit.setText(directory)
                    self.pending_action = "use_existing"
                    self.show_status("Click Apply to switch to the existing database in this folder.")
                    return
                elif action == "copy_current":
                    # Set the path and track the action
                    self.path_edit.setText(directory)
                    self.pending_action = "copy_current"
                    self.show_status("Click Apply to copy your current database here.")
                    return
                # If cancelled, don't set the path
                return

            self.path_edit.setText(directory)

    def on_clear(self):
        self.path_edit.clear()

    def on_apply(self):
        new_dir = self.path_edit.text().strip()
        current_db = self.current_db_path
        new_db = self.resolve_db_path(new_dir)

        # Validate directory if a custom path was given
        if new_dir:
            new_dir_path = Path(new_dir)
            if not new_dir_path.exists():
                try:
                    new_dir_path.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    QMessageBox.warning(
                        self, "Invalid Path",
                        f"Could not create the directory:\n{exc}",
                    )
                    return
            if not new_dir_path.is_dir():
                QMessageBox.warning(
                    self, "Invalid Path",
                    "The selected path is not a directory.",
                )
                return

        if new_db.resolve() == current_db.resolve():
            # Same file; only the stored setting needs updating.
            self.finalize_apply(new_dir, new_db)
            return

        # Work out what the change actually does before warning about it, so the
        # warning always matches the scenario the user is in.
        action = self.pending_action
        if action is None:
            if new_db.exists():
                action = self.prompt_for_existing_db(new_db)
            elif current_db.exists():
                action = self.prompt_for_empty_destination(current_db, new_db)
            else:
                action = "use_existing"
            if action is None:  # Cancelled
                return

        # Security confirmation whenever a custom (external) location is being set.
        if new_dir and not self.confirm_external_location():
            return

        if action == "use_existing" or not current_db.exists():
            if not self.confirm_use_existing(current_db, new_db):
                return
            self.finalize_apply(new_dir, new_db)
            return

        # action == "copy_current"
        if not self.confirm_copy_current(current_db, new_db):
            return

        self.set_controls_enabled(False)
        self.show_status("Copying database\u2026")

        self.copy_worker = DbCopyWorker(current_db, new_db, parent=self)
        self.copy_worker.finished.connect(
            lambda ok, err: self.on_copy_finished(ok, err, new_dir, new_db)
        )
        self.copy_worker.start()

    def on_copy_finished(self, success: bool, error: str, new_dir: str, new_db: Path):
        self.set_controls_enabled(True)
        self.copy_worker = None

        if not success:
            QMessageBox.critical(
                self, "Copy Failed",
                f"Failed to copy the database to the new location:\n{error}",
            )
            self.status_label.hide()
            return

        self.finalize_apply(new_dir, new_db)

    def finalize_apply(self, new_dir: str, new_db: Path):
        """Persist the setting, hot-swap the live DB, and reload the table."""
        try:
            settings = self.window.parent.settings
            saving = settings.setdefault("saving", {})
            db_path_node = saving.setdefault("db_path", {})
            db_path_node["value"] = new_dir

            from utils.file_utils import FileUtils
            FileUtils.write_yaml(self.window.parent.settings_file, settings)
        except Exception as exc:
            QMessageBox.critical(
                self, "Save Failed",
                f"Failed to save the setting:\n{exc}",
            )
            return

        try:
            self.window.swap_database(new_db)
        except Exception as exc:
            logger.exception("Failed to swap database")
            QMessageBox.critical(
                self, "Swap Failed",
                f"Settings saved, but failed to reload the database live:\n{exc}\n\n"
                "Restart QSnippet to apply the change.",
            )
            return

        self.refresh_state()
        self.show_status("Database location updated.")

    def probe_encrypted_rows(self, db_file: Path):
        """Count encrypted rows in a database file that is not the live one.

        Vault key material lives in this device's config file rather than in
        the database, so the encrypted row counts of a database decide what a
        location change actually costs the user.

        Args:
            db_file: Path to a snippets.db file.

        Returns:
            tuple[int, int] | None: (encrypted snippets, encrypted
            placeholders), or None when the file could not be read.
        """
        if not db_file.exists():
            return 0, 0
        try:
            conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                snippets = cur.execute(
                    "SELECT COUNT(*) FROM snippets WHERE is_encrypted = 1"
                ).fetchone()[0]
                placeholders = cur.execute(
                    "SELECT COUNT(*) FROM custom_placeholders WHERE is_encrypted = 1"
                ).fetchone()[0]
                return int(snippets), int(placeholders)
            finally:
                conn.close()
        except Exception:
            logger.warning("Could not read encrypted row counts from %s", db_file)
            return None

    @staticmethod
    def describe_vault_rows(counts) -> str:
        """Render encrypted row counts as a short phrase for a warning dialog."""
        snippets, placeholders = counts
        parts = []
        if snippets:
            parts.append(f"{snippets} vault snippet{'s' if snippets != 1 else ''}")
        if placeholders:
            parts.append(
                f"{placeholders} encrypted placeholder{'s' if placeholders != 1 else ''}"
            )
        return " and ".join(parts)

    def vault_is_configured(self) -> bool:
        """Whether this device holds vault key material in its config."""
        try:
            return self.window.vault_manager().is_setup(self.window.vault_config())
        except Exception:
            return False

    def prompt_for_existing_db(self, destination: Path):
        """
        Prompt the user when destination folder already contains a database.

        Args:
            destination: Path to the destination snippets.db file

        Returns:
            "use_existing" - use the existing database at destination
            "copy_current" - copy the current database over the existing one
            None - cancelled
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Database Already Exists")
        msg.setIcon(QMessageBox.Question)
        msg.setText(
            f"The selected directory already contains a database:\n{destination}"
        )
        msg.setInformativeText(
            "What would you like to do?\n\n"
            "\u2022 Use Existing: open the database in that folder. Your current "
            "snippets stay in their current file; nothing is merged.\n\n"
            "\u2022 Copy Current: copy your current database over the one in that "
            "folder. The existing file is overwritten and cannot be recovered.\n\n"
            "\u2022 Cancel: don't change anything"
        )

        use_btn = msg.addButton("Use Existing", QMessageBox.ActionRole)
        copy_btn = msg.addButton("Copy Current", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)

        msg.exec()
        if msg.clickedButton() == use_btn:
            return "use_existing"
        elif msg.clickedButton() == copy_btn:
            return "copy_current"
        return None

    def prompt_for_empty_destination(self, current_db: Path, destination: Path):
        """
        Prompt when the chosen folder holds no database yet.

        Args:
            current_db: The database currently in use.
            destination: Where the database would live after the change.

        Returns:
            "copy_current" - copy the current database to the new location
            "use_existing" - start a new, empty database there
            None - cancelled
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("No Database In That Folder")
        msg.setIcon(QMessageBox.Question)
        msg.setText(f"There is no database at:\n{destination}")
        msg.setInformativeText(
            "What would you like to do?\n\n"
            f"\u2022 Copy Current: copy the database you are using now "
            f"({current_db}) to that folder and carry on with your existing "
            "snippets.\n\n"
            "\u2022 Start Empty: create a new, empty database there. Your current "
            "snippets are left behind in the old file and will not appear in "
            "QSnippet until you switch back.\n\n"
            "\u2022 Cancel: don't change anything"
        )

        copy_btn = msg.addButton("Copy Current", QMessageBox.ActionRole)
        empty_btn = msg.addButton("Start Empty", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)

        msg.exec()
        if msg.clickedButton() == copy_btn:
            return "copy_current"
        if msg.clickedButton() == empty_btn:
            return "use_existing"
        return None

    def confirm_copy_current(self, current_db: Path, new_db: Path) -> bool:
        """Confirm copying the current database to a new location.

        Spells out the two things that are easy to get wrong here: the copy
        overwrites whatever already sits at the destination, and the vault key
        stays behind on this device even though the encrypted rows travel.

        Args:
            current_db: The database currently in use.
            new_db: Destination database file.

        Returns:
            bool: True when the user confirmed.
        """
        points = []
        if new_db.exists():
            points.append(
                f"\u2022 A database already exists at {new_db}. It will be "
                "overwritten and permanently lost. Anything in it that is not also "
                "in your current database cannot be recovered."
            )
        points.append(
            f"\u2022 This is a copy, not a move. The original file stays at "
            f"{current_db}. Delete it yourself only once you have confirmed the new "
            "location works."
        )

        counts = self.probe_encrypted_rows(current_db)
        if counts is None:
            points.append(
                "\u2022 Your current database could not be inspected for vault "
                "content, so treat the vault note below as applying to it."
            )
            counts = (1, 0)
        if counts[0] or counts[1]:
            described = self.describe_vault_rows(counts)
            points.append(
                f"\u2022 Your {described} are copied across and keep working on "
                "this device: the vault key is derived from your password and the "
                "salt held in this device's config file, which does not move with "
                "the database."
            )
            points.append(
                "\u2022 Another device that opens this same file cannot read those "
                "entries. It derives its own key from its own config, so vault "
                "content fails to decrypt there even with the right password. To "
                "share vault snippets, unlock the vault, export them "
                "(File \u2192 Export, encrypted with your vault password), and "
                "import that file on the other device."
            )

        msg = QMessageBox(self)
        msg.setWindowTitle("Copy Database To New Location")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            f"Your current database will be copied to:\n{new_db}\n\n"
            "QSnippet will then use the copy."
        )
        msg.setInformativeText("\n\n".join(points) + "\n\nContinue?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        return msg.exec() == QMessageBox.Yes

    def confirm_use_existing(self, current_db: Path, new_db: Path) -> bool:
        """Confirm switching to a different database without copying.

        The costly case is a database that already carries vault rows from
        another install: this device cannot decrypt them, and no password will
        change that, so the warning has to say so plainly.

        Args:
            current_db: The database currently in use.
            new_db: The database to switch to.

        Returns:
            bool: True when the user confirmed.
        """
        points = [
            f"\u2022 Your current snippets stay in {current_db}. Nothing is merged "
            "or transferred, and they will not appear in QSnippet until you switch "
            "back to that location."
        ]

        counts = self.probe_encrypted_rows(new_db)
        if counts is None:
            points.append(
                f"\u2022 {new_db} could not be read. It may not be a QSnippet "
                "database, in which case the switch will fail or leave you with an "
                "empty one."
            )
        elif counts[0] or counts[1]:
            described = self.describe_vault_rows(counts)
            if self.vault_is_configured():
                points.append(
                    f"\u2022 That database contains {described}. Vault content is "
                    "encrypted with a key derived from the vault password and the "
                    "salt in the config file of the install that created it, and "
                    "none of that key material lives in the database. If those "
                    "entries came from another install, this device cannot decrypt "
                    "them: they stay unreadable whatever password you enter, while "
                    "your own vault password still applies to entries you create "
                    "from now on."
                )
            else:
                points.append(
                    f"\u2022 That database contains {described}, but no vault is "
                    "set up on this device. QSnippet will flag the vault as needing "
                    "attention and those entries cannot be opened here. Setting up "
                    "a new vault mints a new key and will not recover them."
                )
            points.append(
                "\u2022 The only way to bring vault content across is to export it "
                "from the install that created it (unlock the vault, then "
                "File \u2192 Export, encrypted with that vault password) and import "
                "the file here after switching."
            )

        msg = QMessageBox(self)
        msg.setWindowTitle("Switch To A Different Database")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(f"QSnippet will start using the database at:\n{new_db}")
        msg.setInformativeText("\n\n".join(points) + "\n\nContinue?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        return msg.exec() == QMessageBox.Yes

    def confirm_external_location(self) -> bool:
        """Show a security warning and ask the user to confirm the external location."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Security Warning - External Database Location")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "You are about to store your snippets database outside the default "
            "app data location (e.g. on a cloud drive or network share)."
        )
        msg.setInformativeText(
            "Please read the following before continuing:\n\n"
            "• Cloud providers and SMB/network shares are accessible to third parties. "
            "Any snippets stored in plain text will be readable by your cloud provider, "
            "network administrators, or an attacker who gains access to the share.\n\n"
            "• If your snippets contain sensitive information (passwords, account numbers, "
            "personal details), move them into the Vault first. "
            "Vault snippets are encrypted with AES-256-GCM and are safe to sync.\n\n"
            "• Back up your existing snippets before proceeding. Use "
            "File → Export Snippets to create a local YAML backup.\n\n"
            "\u2022 The vault key does not travel with the database. Its salt and "
            "verifier stay in this device's config file, so a synced database "
            "opened on another device cannot decrypt vault entries created here, "
            "and the reverse is true too. Move vault content between devices with "
            "an encrypted export and import instead.\n\n"
            "Do you understand the risks and want to continue?"
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        return msg.exec() == QMessageBox.Yes

    def set_controls_enabled(self, enabled: bool):
        self.apply_btn.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.path_edit.setEnabled(enabled)

    def show_status(self, message: str):
        self.status_label.setText(message)
        self.status_label.show()

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def applyStyles(self):
        self.apply_header_font()

    def apply_header_font(self):
        """Match the bold/large header font used by dynamically generated settings pages."""
        from ui.theme_manager import ThemeManager
        self.header.setFont(ThemeManager.font("large", bold=True))
