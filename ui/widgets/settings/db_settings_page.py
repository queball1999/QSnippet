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
                elif action == "move_current":
                    # Set the path and track the action
                    self.path_edit.setText(directory)
                    self.pending_action = "move_current"
                    self.show_status("Click Apply to move your current database here.")
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

        path_changing = new_db.resolve() != current_db.resolve()

        # If user selected via browse dialog, use their choice
        if self.pending_action == "use_existing":
            self.finalize_apply(new_dir, new_db)
            return

        if self.pending_action == "move_current":
            should_copy = True
        else:
            # Fallback: if path typed manually and destination has a database, ask user
            if path_changing and new_db.exists():
                action = self.prompt_for_existing_db(new_db)
                if action is None:  # Cancelled
                    return
                if action == "use_existing":
                    self.finalize_apply(new_dir, new_db)
                    return
                should_copy = True
            else:
                should_copy = False

        # Security confirmation whenever a custom (external) location is being set.
        if new_dir and path_changing:
            if not self.confirm_external_location():
                return

        # Copy DB to new location when requested
        if should_copy and path_changing and current_db.exists():
            # Ask for overwrite confirmation if destination has a database
            if new_db.exists():
                reply = QMessageBox.question(
                    self,
                    "File Exists",
                    f"A database file already exists at:\n{new_db}\n\n"
                    "Overwrite it with the current database?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

            self.set_controls_enabled(False)
            self.show_status("Copying database…")

            self.copy_worker = DbCopyWorker(current_db, new_db, parent=self)
            self.copy_worker.finished.connect(
                lambda ok, err: self.on_copy_finished(ok, err, new_dir, new_db)
            )
            self.copy_worker.start()
        else:
            self.finalize_apply(new_dir, new_db)

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

    def prompt_for_existing_db(self, destination: Path):
        """
        Prompt the user when destination folder already contains a database.

        Args:
            destination: Path to the destination snippets.db file

        Returns:
            "use_existing" - use the existing database at destination
            "move_current" - move current database and overwrite existing
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
            "• Use Existing: Switch to the database in this folder\n"
            "• Move Current: Copy your current database here and overwrite the existing one\n"
            "• Cancel: Don't change anything"
        )

        use_btn = msg.addButton("Use Existing", QMessageBox.ActionRole)
        move_btn = msg.addButton("Move Current", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)

        result = msg.exec()
        if msg.clickedButton() == use_btn:
            return "use_existing"
        elif msg.clickedButton() == move_btn:
            return "move_current"
        return None

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
        self.move_switch.setEnabled(enabled)

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
        app = getattr(self.window, "parent", None)
        if not app:
            return

        if hasattr(app, "large_font_size_bold"):
            self.header.setFont(getattr(app, "large_font_size_bold"))
        elif hasattr(app, "large_font_size"):
            font = getattr(app, "large_font_size")
            font.setBold(True)
            self.header.setFont(font)
