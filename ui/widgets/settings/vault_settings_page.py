import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QScrollArea
)
from PySide6.QtCore import QTimer

from ui.widgets.QAnimatedSwitch import QAnimatedSwitch

logger = logging.getLogger(__name__)

TIMEOUT_OPTIONS = [
    ("5 minutes",  5),
    ("15 minutes", 15),
    ("30 minutes", 30),
    ("1 hour",     60),
    ("4 hours",    240),
    ("Never",      0),
]
DEFAULT_TIMEOUT_MINUTES = 15


class VaultSettingsPage(QWidget):
    """Vault configuration panel shown inside the main settings dialog."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.build_ui()
        self.refresh_state()
        self.applyStyles()

    def build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.header = QLabel("Vault")
        self.header.setObjectName("SettingsHeader")
        layout.addWidget(self.header)

        # Body content is nested a bit further right than the header, matching
        # the extra inset dynamically generated pages get from SettingsCard's
        # own internal margin.
        content = QVBoxLayout()
        content.setContentsMargins(8, 0, 0, 0)
        content.setSpacing(12)
        layout.addLayout(content)

        # Status row
        self.status_label = QLabel("Status: Not configured")
        self.status_label.setObjectName("VaultStatusLabel")
        content.addWidget(self.status_label)

        # Description
        desc = QLabel(
            "The Vault encrypts snippets with AES-256-GCM. "
            "It is designed for snippets containing personal information you paste frequently "
            "(addresses, account numbers, etc.).\n\n"
            "The Vault is NOT a replacement for a dedicated password manager."
        )
        desc.setObjectName("SettingsCardDescription")
        desc.setWordWrap(True)
        content.addWidget(desc)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setObjectName("VaultSeparator")
        content.addWidget(sep1)

        # Unlock on launch
        self.launch_switch = QAnimatedSwitch(
            on_text="Prompt to unlock vault on application launch",
            off_text="Prompt to unlock vault on application launch",
        )
        self.launch_switch.stateChanged.connect(self.on_launch_changed)
        content.addWidget(self.launch_switch)

        # Auto-lock timeout
        timeout_row = QHBoxLayout()
        timeout_lbl = QLabel("Auto-lock after:")
        timeout_lbl.setMinimumWidth(160)
        timeout_row.addWidget(timeout_lbl)
        self.timeout_combo = QComboBox()
        self.timeout_combo.setObjectName("VaultField")
        for label, minutes in TIMEOUT_OPTIONS:
            self.timeout_combo.addItem(label, minutes)
        self.timeout_combo.currentIndexChanged.connect(self.on_timeout_changed)
        timeout_row.addWidget(self.timeout_combo)
        timeout_row.addStretch()
        content.addLayout(timeout_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setObjectName("VaultSeparator")
        content.addWidget(sep2)

        # Action buttons
        btn_row = QHBoxLayout()
        self.setup_btn = QPushButton("Set Up Vault")
        self.setup_btn.setObjectName("VaultConfirmBtn")
        self.setup_btn.setToolTip("Configure a vault password to enable encrypted folders")
        self.setup_btn.clicked.connect(self.on_setup)
        btn_row.addWidget(self.setup_btn)

        self.change_btn = QPushButton("Change Password")
        self.change_btn.setObjectName("SnippetFormBtn")
        self.change_btn.setToolTip("Change the vault password")
        self.change_btn.clicked.connect(self.on_change)
        btn_row.addWidget(self.change_btn)

        self.disable_btn = QPushButton("Disable Vault")
        self.disable_btn.setObjectName("SnippetFormBtn")
        self.disable_btn.setToolTip("Disable the vault and decrypt all vault snippets")
        self.disable_btn.clicked.connect(self.on_disable)
        btn_row.addWidget(self.disable_btn)

        btn_row.addStretch()
        content.addLayout(btn_row)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh_state(self):
        try:
            vm = self.window.vault_manager()
            cfg = self.window.vault_config()
            is_setup = vm.is_setup(cfg)
            is_unlocked = vm.is_unlocked()

            if not is_setup:
                self.status_label.setText("Status: Not configured")
                self.setup_btn.show()
                self.change_btn.hide()
                self.disable_btn.hide()
                self.launch_switch.setEnabled(False)
                self.timeout_combo.setEnabled(False)
            elif is_unlocked:
                self.status_label.setText("Status: Unlocked")
                self.setup_btn.hide()
                self.change_btn.show()
                self.disable_btn.show()
                self.launch_switch.setEnabled(True)
                self.timeout_combo.setEnabled(True)
            else:
                self.status_label.setText("Status: Locked")
                self.setup_btn.hide()
                self.change_btn.show()
                self.disable_btn.show()
                self.launch_switch.setEnabled(True)
                self.timeout_combo.setEnabled(True)

            vault_cfg = cfg.get("vault", {})

            self.launch_switch.blockSignals(True)
            self.launch_switch.setChecked(bool(vault_cfg.get("unlock_on_launch", False)))
            self.launch_switch.blockSignals(False)

            saved_timeout = vault_cfg.get("auto_lock_minutes", DEFAULT_TIMEOUT_MINUTES)
            self.timeout_combo.blockSignals(True)
            for i, (_, mins) in enumerate(TIMEOUT_OPTIONS):
                if mins == saved_timeout:
                    self.timeout_combo.setCurrentIndex(i)
                    break
            self.timeout_combo.blockSignals(False)
        except Exception:
            logger.warning("Failed to refresh vault settings page state", exc_info=True)

    def applyStyles(self):
        self.apply_header_font()
        try:
            from ui.theme_manager import ThemeManager
            self.launch_switch.text_font = ThemeManager.font("medium")
            toggle_size = ThemeManager.toggle_size("small")
            if toggle_size is not None:
                self.launch_switch.toggle_size = toggle_size
            self.launch_switch.applyStyles()
        except Exception:
            pass

    def apply_header_font(self):
        """Match the bold/large header font used by dynamically generated settings pages."""
        from ui.theme_manager import ThemeManager
        self.header.setFont(ThemeManager.font("large", bold=True))

    def on_launch_changed(self, checked: bool):
        cfg = dict(self.window.vault_config())
        cfg["vault"] = dict(cfg.get("vault", {}))
        cfg["vault"]["unlock_on_launch"] = checked
        self.save_config(cfg)

    def on_timeout_changed(self):
        minutes = self.timeout_combo.currentData()
        cfg = dict(self.window.vault_config())
        cfg["vault"] = dict(cfg.get("vault", {}))
        cfg["vault"]["auto_lock_minutes"] = minutes
        self.window.vault_manager().set_auto_lock_minutes(minutes)
        self.save_config(cfg)

    def save_config(self, cfg: dict):
        self.window.parent.cfg = cfg
        try:
            from utils.file_utils import FileUtils
            FileUtils.write_yaml(self.window.parent.config_file, cfg)
        except Exception as exc:
            logger.error("Failed to save vault config: %s", exc)

    def on_setup(self):
        self.window.show_vault_settings()
        QTimer.singleShot(200, self.refresh_state)

    def on_change(self):
        self.window.show_vault_settings()
        QTimer.singleShot(200, self.refresh_state)

    def on_disable(self):
        self.window.disable_vault()
        QTimer.singleShot(200, self.refresh_state)
