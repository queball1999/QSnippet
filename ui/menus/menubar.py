from PySide6.QtWidgets import QMenuBar
from PySide6.QtGui import QIcon, QAction, QActionGroup
from PySide6.QtCore import Signal, QSize

class MenuBar(QMenuBar):
    importAction = Signal()
    exportAction = Signal()
    collectLogsRequested = Signal()
    logLevelChanged = Signal(str)
    showAppInfo = Signal()

    def __init__(self, main=None, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        
        self._build_menus()

    def _build_menus(self):
        self.editor = self.parent.editor
        # ----- File Menu -----
        file_menu = self.addMenu("&File")

        new_icon = QIcon.fromTheme("document-new")
        new_act = QAction(new_icon, "New Snippet", self)
        new_act.setShortcut("Ctrl+N")
        new_act.triggered.connect(self.editor.show_new_form)
        file_menu.addAction(new_act)

        save_icon = QIcon.fromTheme("document-save")
        save_act = QAction(save_icon, "Save Snippet", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self.editor.on_save)
        file_menu.addAction(save_act)

        file_menu.addSeparator()

        # --- Import/Export actions ---
        import_icon = QIcon.fromTheme("document-open")
        import_act = QAction(import_icon, "Import", self)
        import_act.setShortcut("Ctrl+I")
        import_act.triggered.connect(self.importAction.emit)
        file_menu.addAction(import_act)

        export_icon = QIcon.fromTheme("folder-open")
        export_act = QAction(export_icon, "Export", self)
        export_act.setShortcut("Ctrl+E")
        export_act.triggered.connect(self.exportAction.emit)
        file_menu.addAction(export_act)

        file_menu.addSeparator()

        close_icon = QIcon.fromTheme("window-close")
        close_icon = QAction(close_icon, "Close", self)
        close_icon.setShortcut("Ctrl+Q")
        close_icon.triggered.connect(self.parent.close)
        file_menu.addAction(close_icon)
        
        exit_icon = QIcon.fromTheme("system-shutdown")
        exit_act = QAction(exit_icon, "Exit", self)
        exit_act.setShortcut("Ctrl+Shift+Q")
        exit_act.triggered.connect(self.parent.exit)
        file_menu.addAction(exit_act)

        # ----- Edit Menu -----
        edit_menu = self.addMenu("Edit")

        undo_icon = QIcon.fromTheme("edit-undo")
        undo_act = QAction(undo_icon, "Undo", self)
        undo_act.setShortcut("Ctrl+Z")
        undo_act.triggered.connect(lambda: self._do_edit_action("undo"))
        edit_menu.addAction(undo_act)

        redo_icon = QIcon.fromTheme("edit-redo")
        redo_act = QAction(redo_icon, "Redo", self)
        redo_act.setShortcut("Ctrl+Y")
        redo_act.triggered.connect(lambda: self._do_edit_action("redo"))
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        cut_icon = QIcon.fromTheme("edit-cut")
        cut_act = QAction(cut_icon, "Cut", self)
        cut_act.setShortcut("Ctrl+X")
        cut_act.triggered.connect(lambda: self._do_edit_action("cut"))
        edit_menu.addAction(cut_act)

        copy_icon = QIcon.fromTheme("edit-copy")
        copy_act = QAction(copy_icon, "Copy", self)
        copy_act.setShortcut("Ctrl+C")
        copy_act.triggered.connect(lambda: self._do_edit_action("copy"))
        edit_menu.addAction(copy_act)

        paste_icon = QIcon.fromTheme("edit-paste")
        paste_act = QAction(paste_icon, "Paste", self)
        paste_act.setShortcut("Ctrl+V")
        paste_act.triggered.connect(lambda: self._do_edit_action("paste"))
        edit_menu.addAction(paste_act)

        # ----- Tools Menu -----
        tools_menu = self.addMenu("Tools")

        # Create top-level submenus with icons
        # FIXME: Need to set icon here
        datetime_icon = QIcon.fromTheme("")
        context_icon = QIcon.fromTheme("preferences-desktop-locale")

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
                "Location": ("{location}", "Insert configured location"),
            }
        }

        # Build submenu items (no icons here)
        for menu, items in placeholders.items():
            for label, (token, tip) in items.items():
                act = QAction(label, self)
                act.setStatusTip(tip)
                act.triggered.connect(lambda checked=False, t=token: self.insert_token(t))
                menu.addAction(act)

        # ----- Help Menu -----
        help_menu = self.addMenu("Help")
        help_menu.setMinimumWidth(150)

        # Collect Logs
        logs_icon = QIcon.fromTheme("folder-open")
        collect_logs_act = QAction(logs_icon, "Collect Logs", self)
        collect_logs_act.setShortcut("F7")
        collect_logs_act.setStatusTip("Export logs to Downloads folder")
        collect_logs_act.triggered.connect(self.collectLogsRequested.emit)
        help_menu.addAction(collect_logs_act)

        # Log Level submenu
        debug_icon = QIcon.fromTheme("document-properties")
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

            act.triggered.connect(lambda checked=False, lvl=level: self._set_log_level(lvl))
            log_level_menu.addAction(act)


        # About App
        about_icon = QIcon.fromTheme("help-about")
        about_act = QAction(about_icon, "About", self)
        about_act.setShortcut("F2")
        about_act.setStatusTip("View information about your installation")
        about_act.triggered.connect(self.showAppInfo.emit)
        help_menu.addAction(about_act)

    # ----- HELPER FUNCTIONS -----
    def _set_log_level(self, level: str):
        """Emit signal with new log level."""
        self.logLevelChanged.emit(level)

    def _do_edit_action(self, action: str):
        """Perform an edit action on the currently focused widget."""
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


    def insert_token(self, token: str):
        """Insert a replacement token at the current cursor position."""
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