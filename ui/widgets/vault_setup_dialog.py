import re
import secrets
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QCheckBox, QComboBox, QApplication, QStackedWidget, QWidget
)
from PySide6.QtCore import Signal, Qt, QThread, QSize

from PySide6.QtGui import QKeySequence, QShortcut, QFont, QIcon

from utils.file_utils import FileUtils
from utils.vault_manager import VaultManager, VAULT_STALE_KEYS
from .password_field import PasswordField
from .QAnimatedSwitch import QAnimatedSwitch
from .settings.settings_toast import SettingsToast

logger = logging.getLogger(__name__)


class VaultWorker(QThread):
    """Background thread that runs a blocking vault operation.

    Emits ``finished(ok, updated_config)`` when the operation completes so the
    main thread can update the UI and persist the result.

    Args:
        operation: Callable that returns ``(bool, dict)``.
        args: Positional arguments forwarded to *operation*.
        kwargs: Keyword arguments forwarded to *operation*.
    """

    finished = Signal(bool, dict)

    def __init__(self, operation, *args, **kwargs):
        super().__init__()
        self.operation = operation
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        """Execute the vault operation and emit the result.

        Returns:
            None
        """
        try:
            ok, updated = self.operation(*self.args, **self.kwargs)
            self.finished.emit(ok, updated)
        except Exception as exc:
            logger.error("VaultWorker error: %s", exc)
            self.finished.emit(False, {})


# Page metrics, shared by every vault page so they line up with each other
PAGE_PAD = 20
HEADER_PAD = 16
PAGE_SPACING = 12

PASSWORD_RULES = [
    (re.compile(r'.{8,}'),        "At least 8 characters"),
    (re.compile(r'[A-Z]'),        "1 uppercase letter"),
    (re.compile(r'[0-9]'),        "1 number"),
    (re.compile(r'[^A-Za-z0-9]'), "1 special character"),
]


def generate_recovery_code() -> str:
    raw = secrets.token_hex(10)  # 20 hex chars → xxxx-xxxx-xxxx-xxxx-xxxx
    return "-".join(raw[i:i + 4] for i in range(0, 20, 4))


class VaultSetupDialog(QDialog):
    """
    Multi-mode vault management dialog.

    mode="setup"   - 3-page wizard: Welcome → Password (regex validated) → Recovery code
    mode="change"  - change existing password
    mode="disable" - disable vault entirely (decrypts all, moves to a folder)
    """

    vaultConfigured = Signal(dict)
    # Raised from the orphaned-data page, handled by the main window
    recoveryRequested = Signal()
    restartSetupRequested = Signal()

    def __init__(self, config: dict, db, mode: str = "setup", parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.mode = mode
        self.vm = VaultManager.get_instance()
        self.pending_password: str = ""
        self.pending_recovery_code: str = ""
        self.cancel_confirmed: bool = False

        titles = {
            "setup":        "Set Up Vault",
            "change":       "Change Vault Password",
            "disable":      "Disable Vault",
            "force_reset":  "Reset Vault Password",
        }
        self.force_reset = mode == "force_reset"
        self.setWindowTitle(titles.get(mode, "Vault"))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(500)
        flags = Qt.Dialog if self.force_reset else Qt.Dialog | Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)

        # Running the setup wizard against a vault that already exists would
        # generate a fresh key and recovery code, orphaning everything the
        # current key encrypted. Say so and stop, rather than let it happen.
        # The key material lives in the config and the data it protects lives
        # in the database, so they can disagree. Classify before building
        # anything: setting up over an existing vault, or over data whose key
        # is gone, mints a new key and strands what the old one protected.
        self.status = self.vm.describe(self.config, self.db)
        self.orphan_snippets = self.status.snippets
        self.orphan_placeholders = self.status.placeholders

        if mode == "setup" and self.status.is_ready:
            logger.warning("Vault setup opened while the vault is already configured")
            self.mode = "already_setup"
            self.setWindowTitle("Vault Already Set Up")
            self.build_already_setup_ui()
            self.applyStyles()
            return

        if mode == "setup" and self.status.is_orphaned:
            logger.warning(
                "Vault setup opened with orphaned data: %s snippets, %s placeholders, "
                "recovery=%s, partial_config=%s",
                self.status.snippets, self.status.placeholders,
                self.status.has_recovery, self.status.partial_config,
            )
            self.mode = "orphaned"
            self.setWindowTitle("Existing Vault Data Found")
            self.build_orphaned_ui()
            self.applyStyles()
            return

        if mode == "setup" and self.status.state == VAULT_STALE_KEYS:
            # Key material with nothing left to protect. Harmless, but it
            # would look like a recoverable vault later, so clear it now.
            logger.warning("Clearing leftover vault key material before setup")
            self.config = self.vm.strip_crypto_material(self.config)
            self.save_config(self.config)

        if mode in ("setup", "force_reset"):
            self.build_wizard_ui()
        elif mode == "change":
            self.build_change_ui()
        elif mode == "disable":
            self.build_disable_ui()

        self.applyStyles()

    # Shared page scaffold

    def vault_icon_label(self, name: str = "lock.svg", size: int = 32) -> QLabel:
        """
        Return a theme-tinted icon label, or an empty one if it won't load.

        Args:
            name (str): Icon file name under assets/icons.
            size (int): Pixel size to render at.

        Returns:
            QLabel: The icon label.
        """
        label = QLabel()
        label.setObjectName("VaultWelcomeIcon")
        label.setAlignment(Qt.AlignCenter)
        try:
            from ui.theme_manager import ThemeManager
            icon = QIcon(FileUtils.icon_path(name))
            if not icon.isNull():
                tm = ThemeManager.get_instance()
                if tm:
                    icon = tm.recolor_icon(icon, tm.icon_color())
                label.setPixmap(icon.pixmap(size, size))
        except Exception:
            logger.debug("Vault page icon %s could not be loaded", name)

        return label

    def build_header(self, title: str, description: str,
                     icon: str = "lock.svg") -> QFrame:
        """
        Build the header block every vault page opens with.

        Left-aligned icon, title and supporting text on a card surface, the
        same shape the settings and placeholder dialogs use, so the vault
        stops looking like a different application.

        Args:
            title (str): Page heading.
            description (str): Supporting text under the heading.
            icon (str): Icon file name.

        Returns:
            QFrame: The header frame.
        """
        header = QFrame()
        header.setObjectName("VaultHeader")

        row = QHBoxLayout(header)
        row.setContentsMargins(PAGE_PAD, HEADER_PAD, PAGE_PAD, HEADER_PAD)
        row.setSpacing(PAGE_SPACING)

        row.addWidget(self.vault_icon_label(icon), 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(PAGE_SPACING // 2)

        title_label = QLabel(title)
        title_label.setObjectName("VaultHeaderTitle")
        title_label.setWordWrap(True)
        text.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setObjectName("VaultHeaderDesc")
            desc_label.setWordWrap(True)
            text.addWidget(desc_label)

        row.addLayout(text, 1)
        return header

    def build_page(self, title: str, description: str,
                   icon: str = "lock.svg") -> tuple[QFrame, QVBoxLayout]:
        """
        Build a standard vault page with its header already in place.

        Args:
            title (str): Page heading.
            description (str): Supporting text under the heading.
            icon (str): Icon file name.

        Returns:
            tuple[QFrame, QVBoxLayout]: The page and its content layout,
                ready for body widgets followed by build_footer().
        """
        page = QFrame()
        page.setObjectName("VaultWizardPage")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(PAGE_PAD, PAGE_PAD, PAGE_PAD, PAGE_PAD)
        layout.setSpacing(PAGE_SPACING)
        layout.addWidget(self.build_header(title, description, icon))

        return page, layout

    def build_footer(self, layout, left=None, right=None) -> None:
        """
        Add the separator and button row every vault page closes with.

        Args:
            layout (QVBoxLayout): The page layout to append to.
            left (list): Buttons pinned to the left, typically Cancel.
            right (list): Buttons pinned to the right, primary action last.

        Returns:
            None
        """
        layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        layout.addWidget(sep)

        row = QHBoxLayout()
        row.setSpacing(PAGE_SPACING)
        for button in (left or []):
            row.addWidget(button)
        row.addStretch()
        for button in (right or []):
            row.addWidget(button)

        layout.addLayout(row)

    # Orphaned vault data

    def count_orphaned_data(self) -> tuple[int, int]:
        """
        Count encrypted rows left in the database without key material.

        Returns:
            tuple[int, int]: (snippets, placeholders); zeros when the
                database can't be queried, so a failure here never blocks
                setting the vault up.
        """
        if self.db is None:
            return 0, 0

        try:
            return self.db.count_encrypted_rows()
        except Exception:
            logger.exception("Could not count orphaned vault data")
            return 0, 0

    def orphan_summary(self) -> str:
        """
        Describe what was found, in plain terms.

        Returns:
            str: A phrase such as "2 snippets and 1 placeholder".
        """
        parts = []
        if self.orphan_snippets:
            noun = "snippet" if self.orphan_snippets == 1 else "snippets"
            parts.append(f"{self.orphan_snippets} {noun}")
        if self.orphan_placeholders:
            noun = "placeholder" if self.orphan_placeholders == 1 else "placeholders"
            parts.append(f"{self.orphan_placeholders} {noun}")

        return " and ".join(parts) if parts else "no items"

    def build_orphaned_ui(self) -> None:
        """
        Offer recovery or a clear-out instead of a fresh setup.

        Returns:
            None
        """
        can_recover = self.status.has_recovery

        if self.status.partial_config:
            cause = (
                "but your vault configuration is incomplete, so the key cannot "
                "be rebuilt from it."
            )
        else:
            cause = (
                "but the key material for it is missing from your configuration. "
                "That happens if the vault was disabled or the config was reset "
                "while the database was kept, or if the database was copied to a "
                "machine that never had the vault set up."
            )

        page, layout = self.build_page(
            "Existing vault data found",
            f"Your database still holds {self.orphan_summary()} encrypted by a "
            f"previous vault, {cause}",
        )

        if can_recover:
            body = (
                "A recovery code was saved for that vault. Enter it to unlock the "
                "data and set a new password.\n\n"
                "If you no longer have the code, you can clear the old data and "
                "start over. That cannot be undone."
            )
        else:
            body = (
                "No recovery code was saved for it, so this data cannot be "
                "decrypted by anyone, including us. Setting up a new vault will "
                "not bring it back.\n\n"
                "Before clearing it, check whether an older copy of config.yaml "
                "survives on another machine or in a backup: it holds the key "
                "material, and restoring it would make your password work again."
            )

        desc = QLabel(body)
        desc.setObjectName("VaultDialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        pill = QLabel(
            f"Encrypted snippets: {self.status.snippets}    "
            f"Encrypted placeholders: {self.status.placeholders}    "
            f"Recovery code saved: {'yes' if can_recover else 'no'}"
        )
        pill.setObjectName("VaultStatusPill")
        layout.addWidget(pill)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SnippetFormBtn")
        cancel_btn.clicked.connect(self.reject)

        self.clear_vault_btn = QPushButton("Clear Old Vault Data")
        self.clear_vault_btn.setObjectName(
            "SnippetFormBtn" if can_recover else "VaultDangerBtn"
        )
        self.clear_vault_btn.clicked.connect(self.clear_orphaned_data)

        right = [self.clear_vault_btn]
        if can_recover:
            self.recover_btn = QPushButton("Use Recovery Code")
            self.recover_btn.setObjectName("VaultConfirmBtn")
            self.recover_btn.setDefault(True)
            self.recover_btn.clicked.connect(self.request_recovery)
            right.append(self.recover_btn)

        self.build_footer(layout, left=[cancel_btn], right=right)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page)

    def request_recovery(self) -> None:
        """
        Hand off to the recovery flow and close.

        Returns:
            None
        """
        logger.info("User chose recovery for orphaned vault data")
        self.recoveryRequested.emit()
        self.reject()

    def clear_orphaned_data(self) -> None:
        """
        Delete the undecryptable rows, after confirming and backing up.

        Returns:
            None
        """
        from PySide6.QtWidgets import QMessageBox

        summary = self.orphan_summary()
        confirmed = QMessageBox.warning(
            self,
            "Clear old vault data?",
            f"This permanently deletes {summary} that can no longer be "
            "decrypted.\n\n"
            "A backup of your database is written to the backups folder first, "
            "but the data inside it stays encrypted and unreadable without the "
            "original password.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return

        try:
            self.db.backup_before_migration()
        except Exception:
            logger.exception("Backup before clearing orphaned vault data failed")

        try:
            snippets, placeholders = self.db.delete_encrypted_rows()
        except Exception:
            logger.exception("Failed to clear orphaned vault data")
            QMessageBox.critical(
                self,
                "Could not clear vault data",
                "The old vault data could not be removed. The log has details.",
            )
            return

        logger.info(
            "Cleared orphaned vault data: %s snippets, %s placeholders",
            snippets, placeholders,
        )
        QMessageBox.information(
            self,
            "Old vault data cleared",
            f"Removed {snippets} snippets and {placeholders} placeholders.\n\n"
            "You can now set up a new vault.",
        )
        self.restartSetupRequested.emit()
        self.reject()

    # Already-configured guard

    def build_already_setup_ui(self) -> None:
        """
        Explain that the vault exists already and offer only a way out.

        Returns:
            None
        """
        page, layout = self.build_page(
            "Your vault is already set up",
            "There is nothing more to do here; you can close this dialog.",
            icon="lock-open.svg",
        )

        desc = QLabel(
            "Setting the vault up a second time would create a new password and "
            "recovery code, and everything encrypted with the current one would "
            "no longer be readable.\n\n"
            "To change your password, use Change Vault Password in Settings. To "
            "unlock the vault, use the padlock in the toolbar."
        )
        desc.setObjectName("VaultDialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if self.status.counted and self.status.has_data:
            pill = QLabel(
                f"Protecting {self.status.snippets} snippets and "
                f"{self.status.placeholders} placeholders"
            )
            pill.setObjectName("VaultStatusPill")
            layout.addWidget(pill)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("VaultConfirmBtn")
        self.close_btn.setDefault(True)
        self.close_btn.clicked.connect(self.reject)

        self.build_footer(layout, right=[self.close_btn])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page)

    # Setup wizard (3 pages)

    def build_wizard_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_welcome_page())
        self.stack.addWidget(self.build_password_page())
        self.stack.addWidget(self.build_recovery_page())
        root.addWidget(self.stack)

        if self.force_reset:
            self.stack.setCurrentIndex(1)
            self.pw_back_btn.hide()
            self.pw_page_title.setText("Reset Vault Password")
            self.pw_page_desc.setText(
                "You unlocked the vault with a recovery code. "
                "Set a new password and save a new recovery code to secure your vault."
            )
            self.complete_btn.setText("Save New Password")
        else:
            self.stack.setCurrentIndex(0)

    def build_welcome_page(self) -> QFrame:
        page, layout = self.build_page(
            "Welcome to QSnippet Vault",
            "A vault folder encrypts its snippets with AES-256-GCM, for personal "
            "information you paste often: addresses, account numbers and the like.",
        )

        desc = QLabel(
            "The vault is not a replacement for a dedicated password manager. "
            "Encryption protects against casual access, not against a determined "
            "attacker with full physical access to your device.\n\n"
            "You will choose a password, then be given a one-time recovery code. "
            "Keep both somewhere safe: without one of them, the contents cannot "
            "be recovered by anyone, including us."
        )
        desc.setObjectName("VaultDialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SnippetFormBtn")
        cancel_btn.clicked.connect(self.reject)

        next_btn = QPushButton("Get Started")
        next_btn.setObjectName("VaultConfirmBtn")
        next_btn.setDefault(True)
        next_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        self.build_footer(layout, left=[cancel_btn], right=[next_btn])
        return page

    def build_password_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("VaultWizardPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(14)

        title = QLabel("Create Vault Password")
        title.setObjectName("VaultDialogTitle")
        layout.addWidget(title)
        self.pw_page_title = title

        desc = QLabel(
            "Your password is never stored. Keep it in a password manager or written down in a safe place. "
            "A recovery code will be generated in the next step."
        )
        desc.setObjectName("VaultDialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        self.pw_page_desc = desc

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        layout.addWidget(sep)

        pw_row = QHBoxLayout()
        pw_lbl = QLabel("Password:")
        pw_lbl.setObjectName("VaultFieldLabel")
        pw_lbl.setMinimumWidth(150)
        pw_row.addWidget(pw_lbl)
        self.new_pw = PasswordField()
        self.new_pw.setObjectName("VaultField")
        self.new_pw.setPlaceholderText("Enter new password")
        self.new_pw.setMaxLength(255)
        self.new_pw.textChanged.connect(self.on_password_changed)
        pw_row.addWidget(self.new_pw)
        layout.addLayout(pw_row)

        confirm_row = QHBoxLayout()
        confirm_lbl = QLabel("Confirm:")
        confirm_lbl.setObjectName("VaultFieldLabel")
        confirm_lbl.setMinimumWidth(150)
        confirm_row.addWidget(confirm_lbl)
        self.confirm_pw = PasswordField()
        self.confirm_pw.setObjectName("VaultField")
        self.confirm_pw.setPlaceholderText("Repeat new password")
        self.confirm_pw.setMaxLength(255)
        self.confirm_pw.textChanged.connect(self.on_password_changed)
        confirm_row.addWidget(self.confirm_pw)
        layout.addLayout(confirm_row)

        hints_frame = QFrame()
        hints_frame.setObjectName("VaultHintsFrame")
        hints_layout = QVBoxLayout(hints_frame)
        hints_layout.setContentsMargins(8, 8, 8, 8)
        hints_layout.setSpacing(4)

        self.required_lbl = QLabel("Password must contain:")
        self.required_lbl.setObjectName("VaultHintLabel")
        hints_layout.addWidget(self.required_lbl)

        self.hint_labels: list[QLabel] = []
        for _, rule_text in PASSWORD_RULES:
            lbl = QLabel(f"  {rule_text}")
            lbl.setObjectName("VaultHintFail")
            hints_layout.addWidget(lbl)
            self.hint_labels.append(lbl)
        self.match_hint = QLabel("  Passwords match")
        self.match_hint.setObjectName("VaultHintFail")
        hints_layout.addWidget(self.match_hint)
        layout.addWidget(hints_frame)

        layout.addStretch()

        btn_row = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.setObjectName("SnippetFormBtn")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_row.addWidget(back_btn)
        self.pw_back_btn = back_btn
        btn_row.addStretch()
        self.pw_continue_btn = QPushButton("Continue")
        self.pw_continue_btn.setObjectName("VaultConfirmBtn")
        self.pw_continue_btn.setEnabled(False)
        self.pw_continue_btn.clicked.connect(self.on_password_continue)
        btn_row.addWidget(self.pw_continue_btn)
        layout.addLayout(btn_row)

        return page

    def build_recovery_page(self) -> QFrame:
        page = QFrame()
        page.setObjectName("VaultWizardPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(14)

        title = QLabel("Save Your Recovery Code")
        title.setObjectName("VaultDialogTitle")
        layout.addWidget(title)

        desc = QLabel(
            "Store this code somewhere safe, such as a password manager or written down on paper. "
            "It can restore vault access if you forget your password. "
            "This code will NOT be shown again."
        )
        desc.setObjectName("VaultDialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        layout.addWidget(sep)

        self.recovery_code_label = QLabel("")
        self.recovery_code_label.setObjectName("VaultRecoveryCode")
        self.recovery_code_label.setAlignment(Qt.AlignCenter)
        self.recovery_code_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        layout.addWidget(self.recovery_code_label)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setObjectName("SnippetFormBtn")
        copy_btn.clicked.connect(self.copy_recovery_code)
        copy_row.addWidget(copy_btn)
        copy_row.addStretch()
        layout.addLayout(copy_row)

        self.copy_toast = SettingsToast(self)

        layout.addSpacing(8)

        self.recovery_ack = QCheckBox(
            "I have securely saved my recovery code and understand it will not be shown again."
        )
        self.recovery_ack.setObjectName("VaultConfirmCheck")
        self.recovery_ack.toggled.connect(lambda checked: self.complete_btn.setEnabled(checked))
        layout.addWidget(self.recovery_ack)

        layout.addStretch()

        btn_row = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.setObjectName("SnippetFormBtn")
        back_btn.clicked.connect(self.on_recovery_back)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        self.complete_btn = QPushButton("Complete Setup")
        self.complete_btn.setObjectName("VaultConfirmBtn")
        self.complete_btn.setEnabled(False)
        self.complete_btn.clicked.connect(self.do_setup)
        btn_row.addWidget(self.complete_btn)
        layout.addLayout(btn_row)

        return page

    def on_password_changed(self) -> None:
        pw = self.new_pw.text()
        confirm = self.confirm_pw.text()
        all_pass = True
        for i, (pattern, rule_text) in enumerate(PASSWORD_RULES):
            ok = bool(pattern.search(pw))
            lbl = self.hint_labels[i]
            lbl.setText(f"  {rule_text}")
            lbl.setProperty("class", "pass" if ok else "fail")
            lbl.setObjectName("VaultHintPass" if ok else "VaultHintFail")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
            all_pass = all_pass and ok

        match_ok = bool(pw and pw == confirm)
        self.match_hint.setText("  Passwords match")
        self.match_hint.setObjectName("VaultHintPass" if match_ok else "VaultHintFail")
        self.match_hint.style().unpolish(self.match_hint)
        self.match_hint.style().polish(self.match_hint)

        self.pw_continue_btn.setEnabled(all_pass and match_ok)

    def on_password_continue(self) -> None:
        self.pending_password = self.new_pw.text()
        self.pending_recovery_code = generate_recovery_code()
        self.recovery_code_label.setText(self.pending_recovery_code)
        self.recovery_ack.setChecked(False)
        self.complete_btn.setEnabled(False)
        self.stack.setCurrentIndex(2)

    def on_recovery_back(self) -> None:
        self.pending_recovery_code = ""
        self.recovery_code_label.clear()
        self.stack.setCurrentIndex(1)

    def copy_recovery_code(self) -> None:
        code = self.recovery_code_label.text()
        if not code:
            return
        try:
            QApplication.clipboard().setText(code)
            self.copy_toast.show_toast("Copied!")
        except Exception:
            self.copy_toast.show_toast("Copy failed")

    def do_setup(self) -> None:
        # Capture and clear pending secrets before any operation so they are
        # not held in self longer than necessary. Python strings are immutable
        # and cannot be zeroed, but clearing the reference limits the window
        # of exposure.
        password = self.pending_password
        recovery = self.pending_recovery_code
        self.pending_password = ""
        self.pending_recovery_code = ""

        if self.force_reset:
            ok, updated = self.vm.force_change_password_authenticated(
                password, recovery, self.config, self.db,
            )
            if not ok:
                return
        else:
            updated = self.vm.setup(password, self.config, recovery)

        self.save_config(updated)
        self.vaultConfigured.emit(updated)
        self.accept()

    # Change password

    def build_change_ui(self) -> None:
        self.change_recovery_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.title_label = QLabel("Change Vault Password")
        self.title_label.setObjectName("VaultDialogTitle")
        layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "All vault snippets will be re-encrypted with the new password."
        )
        self.desc_label.setObjectName("VaultDialogDesc")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        layout.addWidget(sep)

        # Password auth section
        self.change_pw_section = QWidget()
        cps_layout = QVBoxLayout(self.change_pw_section)
        cps_layout.setContentsMargins(0, 0, 0, 0)
        cps_layout.setSpacing(6)
        self.add_field(cps_layout, "Current Password:", "current_pw",
                       placeholder="Current vault password")
        self.change_recovery_link = QLabel('<a href="#">Use a recovery code</a>')
        self.change_recovery_link.setObjectName("VaultRecoveryLink")
        self.change_recovery_link.setAlignment(Qt.AlignLeft)
        self.change_recovery_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.change_recovery_link.linkActivated.connect(
            lambda _: self.set_change_recovery_mode(True))
        cps_layout.addWidget(self.change_recovery_link)
        layout.addWidget(self.change_pw_section)

        # Recovery code section (hidden by default)
        self.change_rec_section = QWidget()
        crs_layout = QVBoxLayout(self.change_rec_section)
        crs_layout.setContentsMargins(0, 0, 0, 0)
        crs_layout.setSpacing(6)
        self.add_field(crs_layout, "Recovery Code:", "change_rec_code",
                       placeholder="xxxx-xxxx-xxxx-xxxx-xxxx")
        self.change_pw_link = QLabel('<a href="#">Use password instead</a>')
        self.change_pw_link.setObjectName("VaultRecoveryLink")
        self.change_pw_link.setAlignment(Qt.AlignRight)
        self.change_pw_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.change_pw_link.linkActivated.connect(
            lambda _: self.set_change_recovery_mode(False))
        crs_layout.addWidget(self.change_pw_link)
        self.change_rec_section.hide()
        layout.addWidget(self.change_rec_section)

        self.add_field(layout, "New Password:", "new_pw",
                        placeholder="Min 8 characters")
        self.add_field(layout, "Confirm Password:", "confirm_pw",
                        placeholder="Repeat new password")

        self.error_label = QLabel("")
        self.error_label.setObjectName("VaultErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SnippetFormBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.confirm_btn = QPushButton("Save")
        self.confirm_btn.setObjectName("VaultConfirmBtn")
        self.confirm_btn.clicked.connect(self.do_change)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        shortcut = QShortcut(QKeySequence("Return"), self)
        shortcut.activated.connect(self.do_change)

    def set_change_recovery_mode(self, enabled: bool) -> None:
        self.change_recovery_mode = enabled
        self.change_pw_section.setVisible(not enabled)
        self.change_rec_section.setVisible(enabled)
        self.error_label.hide()
        if enabled:
            self.change_rec_code.setFocus()
        else:
            self.current_pw.setFocus()

    def do_change(self) -> None:
        use_recovery = getattr(self, "_change_recovery_mode", False)
        if use_recovery:
            if not self.vm.has_recovery(self.config):
                self.show_error(
                    "No recovery code was set up for this vault. "
                    "Enter your current password instead."
                )
                return
            old_credential = self.change_rec_code.text().strip()
            if not old_credential:
                self.show_error("Enter your recovery code.")
                return
        else:
            old_credential = self.current_pw.text()
            if not old_credential:
                self.show_error("Enter your current password.")
                return

        new_pw = self.new_pw.text()
        confirm = self.confirm_pw.text()

        if len(new_pw) < 8:
            self.show_error("New password must be at least 8 characters.")
            return
        if new_pw != confirm:
            self.show_error("New passwords do not match.")
            return

        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setText("Re-encrypting…")

        self.worker = VaultWorker(
            self.vm.change_password,
            old_credential, new_pw, self.config, self.db,
            use_recovery=use_recovery,
        )
        _use_recovery = use_recovery
        self.worker.finished.connect(
            lambda ok, updated: self.on_change_done(ok, updated, _use_recovery)
        )
        self.worker.start()

    def on_change_done(self, ok: bool, updated: dict, use_recovery: bool) -> None:
        """Handle the result of a background password-change operation.

        Args:
            ok: ``True`` when ``change_password`` succeeded.
            updated: Updated config dict returned by the worker.
            use_recovery: Whether recovery-code auth was used (for error text).

        Returns:
            None
        """
        if not ok:
            self.confirm_btn.setEnabled(True)
            self.confirm_btn.setText("Save")
            self.show_error(
                "Incorrect recovery code." if use_recovery else "Incorrect current password."
            )
            return

        self.save_config(updated)
        self.vaultConfigured.emit(updated)
        self.accept()

    # Disable vault

    def build_disable_ui(self) -> None:
        self.disable_recovery_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.title_label = QLabel("Disable Vault Encryption")
        self.title_label.setObjectName("VaultDialogTitle")
        layout.addWidget(self.title_label)

        self.desc_label = QLabel(
            "Enter your vault password, then choose what happens to your encrypted "
            "snippets and placeholders."
        )
        self.desc_label.setObjectName("VaultDialogDesc")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        warn_frame = QFrame()
        warn_frame.setObjectName("VaultWarningBox")
        wl = QVBoxLayout(warn_frame)
        wl.setContentsMargins(12, 8, 12, 8)
        self.disable_warn_text = QLabel()
        self.disable_warn_text.setObjectName("VaultWarningText")
        self.disable_warn_text.setWordWrap(True)
        wl.addWidget(self.disable_warn_text)
        layout.addWidget(warn_frame)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        layout.addWidget(sep)

        # Password auth section
        self.disable_pw_section = QWidget()
        dps_layout = QVBoxLayout(self.disable_pw_section)
        dps_layout.setContentsMargins(0, 0, 0, 0)
        dps_layout.setSpacing(6)
        self.add_field(dps_layout, "Vault Password:", "current_pw",
                       placeholder="Your vault password")
        self.disable_recovery_link = QLabel('<a href="#">Use a recovery code</a>')
        self.disable_recovery_link.setObjectName("VaultRecoveryLink")
        self.disable_recovery_link.setAlignment(Qt.AlignLeft)
        self.disable_recovery_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.disable_recovery_link.linkActivated.connect(
            lambda _: self.set_disable_recovery_mode(True))
        dps_layout.addWidget(self.disable_recovery_link)
        layout.addWidget(self.disable_pw_section)

        # Recovery code section (hidden by default)
        self.disable_rec_section = QWidget()
        drs_layout = QVBoxLayout(self.disable_rec_section)
        drs_layout.setContentsMargins(0, 0, 0, 0)
        drs_layout.setSpacing(6)
        self.add_field(drs_layout, "Recovery Code:", "disable_rec_code",
                       placeholder="xxxx-xxxx-xxxx-xxxx-xxxx")
        self.disable_pw_link = QLabel('<a href="#">Use password instead</a>')
        self.disable_pw_link.setObjectName("VaultRecoveryLink")
        self.disable_pw_link.setAlignment(Qt.AlignRight)
        self.disable_pw_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.disable_pw_link.linkActivated.connect(
            lambda _: self.set_disable_recovery_mode(False))
        drs_layout.addWidget(self.disable_pw_link)
        self.disable_rec_section.hide()
        layout.addWidget(self.disable_rec_section)

        self.delete_data_toggle = QAnimatedSwitch(
            objectName="delete_data_toggle",
            on_text="Delete Permanently",
            off_text="Convert to Plaintext",
            text_position="left",
            toggle_size=QSize(50, 30),
            start_state="off",
            parent=self,
        )
        self.delete_data_toggle.stateChanged.connect(self.on_delete_data_toggled)
        layout.addWidget(self.delete_data_toggle, alignment=Qt.AlignLeft)

        self.target_folder_row = QWidget()
        tf_layout = QHBoxLayout(self.target_folder_row)
        tf_layout.setContentsMargins(0, 0, 0, 0)
        tf_label = QLabel("Destination Folder:")
        tf_label.setObjectName("VaultFieldLabel")
        tf_label.setMinimumWidth(150)
        self.target_folder = QComboBox()
        self.target_folder.setObjectName("VaultField")
        self.target_folder.setEditable(False)
        tf_layout.addWidget(tf_label)
        tf_layout.addWidget(self.target_folder)
        layout.addWidget(self.target_folder_row)
        self.populate_target_folder_combo()
        self.on_delete_data_toggled(self.delete_data_toggle.isChecked())

        self.error_label = QLabel("")
        self.error_label.setObjectName("VaultErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SnippetFormBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.confirm_btn = QPushButton("Disable Vault")
        self.confirm_btn.setObjectName("VaultConfirmBtn")
        self.confirm_btn.clicked.connect(self.do_disable)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        shortcut = QShortcut(QKeySequence("Return"), self)
        shortcut.activated.connect(self.do_disable)

    def populate_target_folder_combo(self) -> None:
        """Populate the destination-folder dropdown with non-vault folders, defaulting to 'Default'."""
        try:
            all_folders = set(self.db.get_all_folders() or [])
            vault_folders = set(self.db.get_vault_folders() or [])
        except Exception:
            all_folders, vault_folders = set(), set()

        folders = sorted(all_folders - vault_folders, key=str.lower)
        if "Default" not in folders:
            folders.insert(0, "Default")

        self.target_folder.clear()
        self.target_folder.addItems(folders)
        default_idx = self.target_folder.findText("Default")
        if default_idx >= 0:
            self.target_folder.setCurrentIndex(default_idx)

    def on_delete_data_toggled(self, checked: bool) -> None:
        """Show the destination-folder picker only when converting to plaintext."""
        self.target_folder_row.setVisible(not checked)
        if checked:
            self.disable_warn_text.setText(
                "WARNING: All encrypted snippets and placeholders will be permanently "
                "deleted. This cannot be undone."
            )
        else:
            self.disable_warn_text.setText(
                "WARNING: All encrypted snippets and placeholders will be permanently "
                "decrypted and moved to the selected folder. Anyone with access to your "
                "device will be able to read them."
            )

    def set_disable_recovery_mode(self, enabled: bool) -> None:
        self.disable_recovery_mode = enabled
        self.disable_pw_section.setVisible(not enabled)
        self.disable_rec_section.setVisible(enabled)
        self.error_label.hide()
        if enabled:
            self.disable_rec_code.setFocus()
        else:
            self.current_pw.setFocus()

    def do_disable(self) -> None:
        use_recovery = getattr(self, "_disable_recovery_mode", False)
        if use_recovery:
            if not self.vm.has_recovery(self.config):
                self.show_error(
                    "No recovery code was set up for this vault. "
                    "Enter your vault password instead."
                )
                return
            credential = self.disable_rec_code.text().strip()
            if not credential:
                self.show_error("Enter your recovery code.")
                return
        else:
            credential = self.current_pw.text()
            if not credential:
                self.show_error("Enter your vault password to confirm.")
                return

        delete_data = self.delete_data_toggle.isChecked()
        folder = ""
        if not delete_data:
            folder = self.target_folder.currentText().strip() or "Default"

        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setText("Deleting..." if delete_data else "Decrypting...")

        self.worker = VaultWorker(
            self.vm.disable_vault,
            credential, self.config, self.db, folder,
            use_recovery=use_recovery,
            delete_data=delete_data,
        )
        _use_recovery = use_recovery
        self.worker.finished.connect(
            lambda ok, updated: self.on_disable_done(ok, updated, _use_recovery)
        )
        self.worker.start()

    def on_disable_done(self, ok: bool, updated: dict, use_recovery: bool) -> None:
        """Handle the result of a background vault-disable operation.

        Args:
            ok: ``True`` when ``disable_vault`` succeeded.
            updated: Updated config dict returned by the worker.
            use_recovery: Whether recovery-code auth was used (for error text).

        Returns:
            None
        """
        if not ok:
            self.confirm_btn.setEnabled(True)
            self.confirm_btn.setText("Disable Vault")

            # A disable that authenticated but could not decrypt everything
            # stops with the key material intact rather than stranding what
            # is left, and has to say so instead of blaming the password.
            failures = getattr(self.vm, "last_disable_failures", [])
            if failures:
                count = len(failures)
                noun = "item" if count == 1 else "items"
                self.show_error(
                    f"{count} {noun} could not be decrypted, so the vault was left "
                    "enabled. Nothing was lost. See the log for details."
                )
                return

            self.show_error(
                "Incorrect recovery code." if use_recovery else "Incorrect vault password."
            )
            return

        self.save_config(updated)
        self.vaultConfigured.emit(updated)
        self.accept()

    # Shared helpers

    def add_field(self, layout, label_text: str, attr: str,
                   placeholder: str = "", is_password: bool = True) -> None:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setObjectName("VaultFieldLabel")
        lbl.setMinimumWidth(150)
        row.addWidget(lbl)
        field = PasswordField() if is_password else QLineEdit()
        field.setObjectName("VaultField")
        field.setPlaceholderText(placeholder)
        if is_password:
            field.setMaxLength(255)
        row.addWidget(field)
        layout.addLayout(row)
        setattr(self, attr, field)

    def show_error(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.show()

    def clear_sensitive_fields(self) -> None:
        for attr in ("new_pw", "confirm_pw", "current_pw", "change_rec_code", "disable_rec_code"):
            field = getattr(self, attr, None)
            if field:
                field.clear()
        self.pending_password = ""
        self.pending_recovery_code = ""
        if hasattr(self, "recovery_code_label"):
            self.recovery_code_label.clear()

    def confirm_cancel_setup(self) -> bool:
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(
            self,
            "Cancel Vault Setup?",
            "Are you sure you want to exit?\n\n"
            "Your vault will not be set up and nothing will be saved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def reject(self) -> None:
        if self.force_reset:
            return
        if self.mode == "setup" and not self.cancel_confirmed:
            if not self.confirm_cancel_setup():
                return
            self.cancel_confirmed = True
        self.clear_sensitive_fields()
        super().reject()

    def closeEvent(self, event) -> None:
        if self.force_reset:
            event.ignore()
            return
        if self.mode == "setup" and not self.cancel_confirmed:
            if not self.confirm_cancel_setup():
                event.ignore()
                return
            self.cancel_confirmed = True
        self.clear_sensitive_fields()
        super().closeEvent(event)

    def save_config(self, config: dict) -> None:
        try:
            from utils.file_utils import FileUtils
            from ui.theme_manager import ThemeManager
            main = ThemeManager.app_instance()
            if main and hasattr(main, "config_file"):
                FileUtils.write_yaml(main.config_file, config)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Failed to persist vault config: %s", exc)

    def applyStyles(self) -> None:
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_fonts(self)
        if hasattr(self, "copy_toast"):
            self.copy_toast.applyStyles()
