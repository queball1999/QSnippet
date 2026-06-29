from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut

from utils.vault_manager import VaultManager
from .password_field import PasswordField


class VaultUnlockDialog(QDialog):
    """
    Prompts for the vault password and unlocks VaultManager on success.
    Emits unlocked(True) on success; the dialog closes automatically.
    Supports recovery code as an alternative to the password.
    """

    unlocked = Signal(bool)

    def __init__(self, config: dict, parent=None, message: str = ""):
        super().__init__(parent)
        self.config = config
        self.vm = VaultManager.get_instance()
        self.recovery_mode = False
        self.recovery_was_used = False

        self.setWindowTitle("Unlock Vault")
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(380)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        self.build_ui(message)
        self.applyStyles()

        shortcut = QShortcut(QKeySequence("Return"), self)
        shortcut.activated.connect(self.attempt_unlock)

    def build_ui(self, message: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        self.title_label = QLabel("Vault Locked")
        self.title_label.setObjectName("VaultDialogTitle")
        layout.addWidget(self.title_label)

        body_text = message if message else "Enter your vault password to access encrypted snippets."
        self.body_label = QLabel(body_text)
        self.body_label.setObjectName("VaultDialogDesc")
        self.body_label.setWordWrap(True)
        layout.addWidget(self.body_label)

        # Password auth section
        self.pw_section = QWidget()
        pw_layout = QVBoxLayout(self.pw_section)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(6)

        pw_row = QHBoxLayout()
        pw_lbl = QLabel("Password:")
        pw_lbl.setObjectName("VaultFieldLabel")
        pw_lbl.setMinimumWidth(90)
        pw_row.addWidget(pw_lbl)
        self.pw_field = PasswordField()
        self.pw_field.setObjectName("VaultField")
        self.pw_field.setPlaceholderText("Vault password")
        pw_row.addWidget(self.pw_field)
        pw_layout.addLayout(pw_row)

        self.recovery_link = QLabel('<a href="#">Use recovery code</a>')
        self.recovery_link.setObjectName("VaultRecoveryLink")
        self.recovery_link.setAlignment(Qt.AlignLeft)
        self.recovery_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.recovery_link.linkActivated.connect(lambda _: self.set_recovery_mode(True))
        pw_layout.addWidget(self.recovery_link)

        layout.addWidget(self.pw_section)

        # Recovery code section (hidden by default)
        self.rec_section = QWidget()
        rec_layout = QVBoxLayout(self.rec_section)
        rec_layout.setContentsMargins(0, 0, 0, 0)
        rec_layout.setSpacing(6)

        rec_row = QHBoxLayout()
        rec_lbl = QLabel("Recovery code:")
        rec_lbl.setObjectName("VaultFieldLabel")
        rec_lbl.setMinimumWidth(90)
        rec_row.addWidget(rec_lbl)
        self.rec_field = PasswordField()
        self.rec_field.setObjectName("VaultField")
        self.rec_field.setPlaceholderText("xxxx-xxxx-xxxx-xxxx-xxxx")
        rec_row.addWidget(self.rec_field)
        rec_layout.addLayout(rec_row)

        self.pw_link = QLabel('<a href="#">Use password instead</a>')
        self.pw_link.setObjectName("VaultRecoveryLink")
        self.pw_link.setAlignment(Qt.AlignRight)
        self.pw_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.pw_link.linkActivated.connect(lambda _: self.set_recovery_mode(False))
        rec_layout.addWidget(self.pw_link)

        self.rec_section.hide()
        layout.addWidget(self.rec_section)

        self.error_label = QLabel("")
        self.error_label.setObjectName("VaultErrorLabel")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SnippetFormBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        self.unlock_btn = QPushButton("Unlock")
        self.unlock_btn.setObjectName("VaultConfirmBtn")
        self.unlock_btn.clicked.connect(self.attempt_unlock)
        btn_row.addWidget(self.unlock_btn)
        layout.addLayout(btn_row)

    def set_recovery_mode(self, enabled: bool) -> None:
        self.recovery_mode = enabled
        self.pw_section.setVisible(not enabled)
        self.rec_section.setVisible(enabled)
        self.error_label.hide()
        if enabled:
            self.rec_field.setFocus()
        else:
            self.pw_field.setFocus()

    def attempt_unlock(self) -> None:
        if self.recovery_mode:
            if not self.vm.has_recovery(self.config):
                self.error_label.setText(
                    "No recovery code was set up for this vault. "
                    "Change your vault password from Settings to enable recovery."
                )
                self.error_label.show()
                return
            code = self.rec_field.text().strip()
            if not code:
                self.rec_field.setFocus()
                return
            self.unlock_btn.setEnabled(False)
            self.unlock_btn.setText("Verifying…")
            if self.vm.unlock_with_recovery_code(code, self.config):
                self.recovery_was_used = True
                self.unlocked.emit(True)
                self.accept()
            else:
                self.unlock_btn.setEnabled(True)
                self.unlock_btn.setText("Unlock")
                self.error_label.setText("Invalid recovery code.")
                self.error_label.show()
                self.rec_field.clear()
                self.rec_field.setFocus()
        else:
            pw = self.pw_field.text()
            if not pw:
                self.pw_field.setFocus()
                return
            self.unlock_btn.setEnabled(False)
            self.unlock_btn.setText("Unlocking…")
            if self.vm.unlock(pw, self.config):
                self.unlocked.emit(True)
                self.accept()
            else:
                self.unlock_btn.setEnabled(True)
                self.unlock_btn.setText("Unlock")
                self.error_label.setText("Incorrect password.")
                self.error_label.show()
                self.pw_field.clear()
                self.pw_field.setFocus()

    def closeEvent(self, event) -> None:
        self.pw_field.clear()
        self.rec_field.clear()
        super().closeEvent(event)

    def applyStyles(self) -> None:
        try:
            main = getattr(self.parent(), "parent", None)
            if main and hasattr(main, "medium_font_size"):
                mf = main.medium_font_size
                sf = main.small_font_size
                self.title_label.setFont(main.large_font_size_bold)
                self.body_label.setFont(sf)
                self.pw_field.setFont(mf)
                self.rec_field.setFont(mf)
                self.cancel_btn.setFont(mf)
                self.unlock_btn.setFont(mf)
                self.recovery_link.setFont(sf)
                self.pw_link.setFont(sf)
                for lbl in self.findChildren(QLabel, "VaultFieldLabel"):
                    lbl.setFont(mf)
        except Exception:
            pass
