from PySide6.QtWidgets import QMenuBar
from PySide6.QtGui import QIcon, QAction, QActionGroup
from PySide6.QtCore import Signal, QUrl
from PySide6.QtGui import QDesktopServices

from utils.file_utils import FileUtils

class MenuBar(QMenuBar):
    """
    MenuBar is the main menu bar for the application, providing access to file, edit,
    tools, and help menus with various actions and shortcuts.
    """
    importAction = Signal()
    exportAction = Signal()
    renameAction = Signal()
    collectLogsRequested = Signal()
    viewBackupHistoryRequested = Signal()
    logLevelChanged = Signal(str)
    showAppInfo = Signal()
    show_settings = Signal()
    showPlaceholderManager = Signal()

    def __init__(self, main=None, parent=None):
        """
        Initialize the MenuBar with all application menus.

        Args:
            main (Any): Reference to the main application object.
            parent (QWidget): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.main = main
        self.parent = parent
        
        self.build_menus()

    def build_menus(self):
        """
        Build all menu structures (File, Edit, Tools, Help).

        Creates and configures all menus including file operations, edit actions,
        tool shortcuts, and help resources with associated signals and shortcuts.

        Returns:
            None
        """
        self.editor = self.parent.editor
        # ----- File Menu -----
        file_menu = self.addMenu("&File")

        new_icon = QIcon(FileUtils.icon_path("note-plus-outline.svg"))
        new_act = QAction(new_icon, "New Snippet", self)
        new_act.setShortcut("Ctrl+N")
        new_act.triggered.connect(self.editor.show_new_form)
        file_menu.addAction(new_act)

        save_icon = QIcon(FileUtils.icon_path("content-save-outline.svg"))
        save_act = QAction(save_icon, "Save Snippet", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self.editor.on_save)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        # --- Import/Export actions ---
        import_icon = QIcon(FileUtils.icon_path("file-import-outline.svg"))
        import_act = QAction(import_icon, "Import", self)
        import_act.setShortcut("Ctrl+I")
        import_act.triggered.connect(self.importAction.emit)
        file_menu.addAction(import_act)

        export_icon = QIcon(FileUtils.icon_path("file-export-outline.svg"))
        export_act = QAction(export_icon, "Export", self)
        export_act.setShortcut("Ctrl+E")
        export_act.triggered.connect(self.exportAction.emit)
        file_menu.addAction(export_act)

        file_menu.addSeparator()

        close_icon = QIcon(FileUtils.icon_path("close.svg"))
        close_act = QAction(close_icon, "Close", self)
        close_act.setShortcut("Ctrl+Q")
        close_act.triggered.connect(self.parent.close)
        file_menu.addAction(close_act)

        exit_icon = QIcon(FileUtils.icon_path("quit.svg"))
        exit_act = QAction(exit_icon, "Exit", self)
        exit_act.setShortcut("Ctrl+Shift+Q")
        exit_act.triggered.connect(self.parent.exit)
        file_menu.addAction(exit_act)

        # ----- Edit Menu -----
        edit_menu = self.addMenu("Edit")

        undo_icon = QIcon(FileUtils.icon_path("undo-arrow.svg"))
        undo_act = QAction(undo_icon, "Undo", self)
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(lambda: self.do_edit_action("undo"))
        edit_menu.addAction(undo_act)

        redo_icon = QIcon(FileUtils.icon_path("redo-arrow.svg"))
        redo_act = QAction(redo_icon, "Redo", self)
        redo_act.setShortcut("Ctrl+Y")
        redo_act.triggered.connect(lambda: self.do_edit_action("redo"))
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        cut_icon = QIcon(FileUtils.icon_path("content-cut.svg"))
        cut_act = QAction(cut_icon, "Cut", self)
        cut_act.setShortcut("Ctrl+X")
        cut_act.triggered.connect(lambda: self.do_edit_action("cut"))
        edit_menu.addAction(cut_act)

        copy_icon = QIcon(FileUtils.icon_path("content-copy.svg"))
        copy_act = QAction(copy_icon, "Copy", self)
        copy_act.setShortcut("Ctrl+C")
        copy_act.triggered.connect(lambda: self.do_edit_action("copy"))
        edit_menu.addAction(copy_act)

        paste_icon = QIcon(FileUtils.icon_path("content-paste.svg"))
        paste_act = QAction(paste_icon, "Paste", self)
        paste_act.setShortcut("Ctrl+V")
        paste_act.triggered.connect(lambda: self.do_edit_action("paste"))
        edit_menu.addAction(paste_act)

        edit_menu.addSeparator()
        rename_icon = QIcon(FileUtils.icon_path("rename.svg"))
        rename_act = QAction(rename_icon, "Rename", self)
        rename_act.setShortcut("F2")
        rename_act.triggered.connect(lambda: self.do_edit_action("rename"))
        edit_menu.addAction(rename_act)

        edit_menu.addSeparator()
        settings_icon = QIcon(FileUtils.icon_path("settings-outline.svg"))
        settings_act = QAction(settings_icon, "Settings", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.triggered.connect(self.show_settings.emit)
        edit_menu.addAction(settings_act)

        # ----- Tools Menu -----
        tools_menu = self.addMenu("Tools")

        # Create top-level submenus with icons
        datetime_icon = QIcon(FileUtils.icon_path("calendar-clock-outline.svg"))
        context_icon = QIcon(FileUtils.icon_path("earth.svg"))

        datetime_menu = tools_menu.addMenu(datetime_icon, "Date/Time")
        context_menu  = tools_menu.addMenu(context_icon, "Context")

        # Define token groups (no icons for individual items)
        placeholders = {
            datetime_menu: {
                "Date": ("{date}", "Insert date (YYYY-MM-DD)"),
                "Date (long)": ("{date_long}", "Insert long date"),
                "Time": ("{time}", "Insert time (24hr)"),
                "Time (12hr)": ("{time_ampm}", "Insert time (12hr)"),
                "Date & Time": ("{datetime}", "Insert full datetime"),
                "Weekday": ("{weekday}", "Insert weekday name"),
                "Month": ("{month}", "Insert month name"),
                "Year": ("{year}", "Insert year"),
            },
            context_menu: {
                "Greeting": ("{greeting}", "Insert context-aware greeting"),
                "Location": ("{location}", "Insert user-defined location"),
            }
        }

        # Build submenu items (no icons here)
        for menu, items in placeholders.items():
            for label, (token, tip) in items.items():
                act = QAction(label, self)
                act.setStatusTip(tip)
                act.triggered.connect(lambda checked=False, t=token: self.insert_token(t))
                menu.addAction(act)

        # Custom placeholders submenu
        custom_icon = QIcon(FileUtils.icon_path("card-text-outline.svg"))
        self.custom_ph_menu = tools_menu.addMenu(custom_icon, "Custom")
        self.custom_ph_items_start = None  # separator before dynamic items
        self.build_custom_placeholder_menu_static()

        # ----- Help Menu -----
        help_menu = self.addMenu("Help")
        help_menu.setMinimumWidth(150)

        # Collect Logs
        logs_icon = QIcon(FileUtils.icon_path("folder-open-outline.svg"))
        collect_logs_act = QAction(logs_icon, "Collect Logs", self)
        collect_logs_act.setShortcut("F7")
        collect_logs_act.setStatusTip("Export logs to Downloads folder")
        collect_logs_act.triggered.connect(self.collectLogsRequested.emit)
        help_menu.addAction(collect_logs_act)

        # Backup History
        backup_icon = QIcon(FileUtils.icon_path("folder-open-outline.svg"))
        backup_history_act = QAction(backup_icon, "Backup History", self)
        backup_history_act.setStatusTip("View automatic database backups made before updates")
        backup_history_act.triggered.connect(self.viewBackupHistoryRequested.emit)
        help_menu.addAction(backup_history_act)

        # Report a Bug
        bug_icon = QIcon(FileUtils.icon_path("bug-outline.svg"))
        report_bug_act = QAction(bug_icon, "Report a Bug", self)
        report_bug_act.setStatusTip("Open the GitHub bug report form")
        report_bug_act.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/queball1999/QSnippet/issues/new?template=bug_report.md")
            )
        )
        help_menu.addAction(report_bug_act)

        # Log Level submenu
        debug_icon = QIcon(FileUtils.icon_path("wrench-outline.svg"))
        log_level_menu = help_menu.addMenu(debug_icon, "Log Level")
        log_level_menu.setStatusTip("Set log level within application")

        # Create an exclusive action group (only one checked at a time)
        self.log_level_group = QActionGroup(self)
        self.log_level_group.setExclusive(True)

        for level in ["ERROR", "WARNING", "INFO", "DEBUG"]:
            act = QAction(level, self)
            act.setCheckable(True)

            # Add action to group to enforce single selection
            self.log_level_group.addAction(act)

            # Mark current log level
            log_level = self.main.log_level if hasattr(self.main, "log_level") else "ERROR"
            if level == log_level:
                act.setChecked(True)

            act.triggered.connect(lambda checked=False, lvl=level: self.set_log_level(lvl))
            log_level_menu.addAction(act)


        # About App
        about_icon = QIcon(FileUtils.icon_path("information-outline.svg"))
        about_act = QAction(about_icon, "About", self)
        about_act.setShortcut("F12")
        about_act.setStatusTip("View information about your installation")
        about_act.triggered.connect(self.showAppInfo.emit)
        help_menu.addAction(about_act)

        # Collect all icon-bearing actions and apply initial tint
        self.collect_icon_actions()
        self.update_icons()
        self.connect_theme()

    # ----- VAULT -----

    def update_vault_state(self, is_setup: bool, is_unlocked: bool) -> None:
        """No-op - vault state is shown in the toolbar only."""

    # ----- ICON THEMING -----

    def collect_icon_actions(self):
        """Walk every menu recursively and store actions that carry an icon."""
        self.icon_sources: dict[QAction, QIcon] = {}

        def walk(menu):
            for action in menu.actions():
                if action.isSeparator():
                    continue
                if not action.icon().isNull():
                    self.icon_sources[action] = action.icon()
                sub = action.menu()
                if sub:
                    walk(sub)

        for top in self.actions():
            sub = top.menu()
            if sub:
                walk(sub)

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

    # ----- PLACEHOLDER MENU -----

    def build_custom_placeholder_menu_static(self):
        """
        Add the static 'Manage Placeholders' action to the Custom submenu.
        Called once during menu construction.
        """
        manage_act = QAction("Manage Placeholders   ", self)
        manage_act.setShortcut("F6")
        manage_act.setStatusTip("Add, edit, or delete user-defined placeholders")
        manage_act.triggered.connect(self.showPlaceholderManager.emit)
        self.custom_ph_menu.addAction(manage_act)
        self.custom_ph_menu.addSeparator()
        # Store where dynamic token actions begin (after separator)
        self.dynamic_ph_separator = self.custom_ph_menu.actions()[-1]

    def rebuild_custom_placeholder_menu(self, placeholders: list):
        """
        Dynamically rebuild the user-defined token items in the Custom submenu.

        Removes all actions after the separator and re-adds them from *placeholders*.

        Args:
            placeholders (list[dict]): Each dict has keys 'name', 'value', 'description'.
        """
        # Remove all actions that come after the separator
        actions = self.custom_ph_menu.actions()
        sep_index = actions.index(self.dynamic_ph_separator) if self.dynamic_ph_separator in actions else -1
        for act in actions[sep_index + 1:]:
            self.custom_ph_menu.removeAction(act)

        if not placeholders:
            placeholder_act = QAction("No custom placeholders defined", self)
            placeholder_act.setEnabled(False)
            self.custom_ph_menu.addAction(placeholder_act)
            return

        for ph in placeholders:
            token = "{" + ph["name"] + "}"
            tip = ph.get("description") or f"Insert {token}"
            act = QAction(ph["name"], self)
            act.setStatusTip(tip)
            act.triggered.connect(lambda checked=False, t=token: self.insert_token(t))
            self.custom_ph_menu.addAction(act)

    # ----- HELPER FUNCTIONS -----
    def set_log_level(self, level: str):
        """
        Emit a signal to change the application log level.

        Args:
            level (str): The log level to set (e.g., "ERROR", "WARNING", "INFO", "DEBUG").

        Returns:
            None
        """
        self.logLevelChanged.emit(level)

    def do_edit_action(self, action: str):
        """
        Perform edit actions on the currently focused widget.

        Handles standard edit operations including undo, redo, cut, copy, paste,
        and rename, delegating to the focused widget's methods where available.

        Args:
            action (str): The edit action to perform (undo, redo, cut, copy, paste, rename).

        Returns:
            None
        """
        widget = self.main.app.focusWidget()
        if not widget:
            return

        # Handle the actions
        if action == "undo" and hasattr(widget, "undo"):
            widget.undo()
        elif action == "redo" and hasattr(widget, "redo"):
            widget.redo()
        elif action == "cut" and hasattr(widget, "cut"):
            widget.cut()
        elif action == "copy" and hasattr(widget, "copy"):
            widget.copy()
        elif action == "paste" and hasattr(widget, "paste"):
            widget.paste()
        elif action == "rename":
            self.renameAction.emit()

    def insert_token(self, token: str):
        """
        Insert a replacement token at the current cursor position in the focused widget.

        Supports insertion into QTextEdit, QPlainTextEdit, and QLineEdit widgets.
        Falls back to the insert() method if specialized cursor methods aren't available.

        Args:
            token (str): The token string to insert (e.g., "{date}", "{time}").

        Returns:
            None
        """
        widget = self.main.app.focusWidget()
        if not widget:
            return

        # QTextEdit / QPlainTextEdit
        if hasattr(widget, "textCursor") and hasattr(widget, "setTextCursor"):
            cursor = widget.textCursor()
            cursor.insertText(token)
            widget.setTextCursor(cursor)

        # QLineEdit
        elif hasattr(widget, "cursorPosition") and hasattr(widget, "setCursorPosition"):
            pos = widget.cursorPosition()
            current = widget.text()
            new_text = current[:pos] + token + current[pos:]
            widget.setText(new_text)
            widget.setCursorPosition(pos + len(token))

        # Fallback
        elif hasattr(widget, "insert"):
            widget.insert(token)

