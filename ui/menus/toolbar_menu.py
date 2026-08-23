from PySide6.QtWidgets import QToolBar
from PySide6.QtGui import QIcon, QAction

from utils.file_utils import FileUtils


class ToolbarMenu(QToolBar):
    """
    ToolbarMenu is the main toolbar for the application, providing quick access
    to common actions such as creating, saving, and deleting snippets.

    Icons are tinted at construction time and whenever the active theme changes
    so they remain visible in both dark and light modes.
    """

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.parent = parent
        self.icon_sources: dict[QAction, QIcon] = {}
        self.vault_lock_icon = QIcon(FileUtils.icon_path("lock.svg"))
        self.vault_open_icon = QIcon(FileUtils.icon_path("lock-open.svg"))
        self.settings_icon = QIcon(FileUtils.icon_path("settings-outline.svg"))
        self.init_actions()
        self.update_icons()
        self.connect_theme()

    def init_actions(self):
        self.editor = self.parent.editor

        self.make_action("home-variant-outline", "Home",           self.editor.show_home_widget)
        self.make_action("note-plus-outline",     "New Snippet",    self.editor.show_new_form)
        self.make_action("content-save-outline",  "Save Snippet",   self.editor.on_save)
        self.make_action("delete-outline",        "Delete Snippet", self.editor.on_delete)

        self.addSeparator()
        self.vault_action = QAction("Vault", self)
        self.vault_action.setToolTip("Vault not configured - click to set up")
        self.vault_action.triggered.connect(self.on_vault_clicked)
        self.addAction(self.vault_action)
        self.icon_sources[self.vault_action] = self.vault_lock_icon

        self.addSeparator()
        self.settings_action = QAction("Settings", self)
        self.settings_action.setToolTip("Open Settings")
        self.settings_action.triggered.connect(self.on_settings_clicked)
        self.addAction(self.settings_action)
        self.icon_sources[self.settings_action] = self.settings_icon

    def update_vault_state(self, is_setup: bool, is_unlocked: bool,
                           needs_attention: bool = False) -> None:
        """Update the vault toolbar button icon and tooltip to reflect current state.

        Args:
            is_setup (bool): Vault has usable key material.
            is_unlocked (bool): Vault is currently unlocked.
            needs_attention (bool): Encrypted data exists with no key for it,
                so clicking leads to recovery rather than to setup.
        """
        if not is_setup and needs_attention:
            icon = self.vault_lock_icon
            tooltip = "Vault data found without its key - click to recover or clear"
        elif not is_setup:
            icon = self.vault_lock_icon
            tooltip = "Vault not configured - click to set up"
        elif is_unlocked:
            icon = self.vault_open_icon
            tooltip = "Vault is unlocked - click to lock"
        else:
            icon = self.vault_lock_icon
            tooltip = "Vault is locked - click to unlock"

        self.icon_sources[self.vault_action] = icon
        self.vault_action.setToolTip(tooltip)

        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        if tm:
            self.vault_action.setIcon(tm.recolor_icon(icon, tm.icon_color()))
        else:
            self.vault_action.setIcon(icon)

    def on_vault_clicked(self) -> None:
        if hasattr(self.parent, "toggle_vault_lock"):
            self.parent.toggle_vault_lock()

    def on_settings_clicked(self) -> None:
        if hasattr(self.parent, "show_settings_window"):
            self.parent.show_settings_window()

    def make_action(self, icon_name: str, label: str, slot) -> QAction:
        icon   = QIcon(FileUtils.icon_path(f"{icon_name}.svg"))
        action = QAction(label, self)
        action.triggered.connect(slot)
        self.addAction(action)
        self.icon_sources[action] = icon   # keep original for re-tinting
        return action

    def connect_theme(self):
        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        if tm:
            tm.themeChanged.connect(self.update_icons)

    def update_icons(self):
        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        if tm is None:
            return
        color = tm.icon_color()
        for action, orig_icon in self.icon_sources.items():
            action.setIcon(tm.recolor_icon(orig_icon, color))
