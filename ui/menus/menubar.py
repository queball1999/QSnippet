from PySide6.QtWidgets import QMenuBar
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal
from utils import FileUtils

class MenuBar(QMenuBar):
    importAction = Signal()
    exportAction = Signal()

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
        import_icon = QIcon.fromTheme("document-import")
        import_act = QAction(import_icon, "Import", self)
        import_act.triggered.connect(self.importAction.emit)
        file_menu.addAction(import_act)

        export_icon = QIcon.fromTheme("document-export")
        export_act = QAction(export_icon, "Export", self)
        export_act.triggered.connect(self.exportAction.emit)
        file_menu.addAction(export_act)

        file_menu.addSeparator()

        close_icon = QIcon.fromTheme("application-close")
        close_icon = QAction(close_icon, "Close", self)
        close_icon.setShortcut("Ctrl+Q")
        close_icon.triggered.connect(self.parent.close)
        file_menu.addAction(close_icon)
        
        exit_icon = QIcon.fromTheme("application-exit")
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
        # These placeholders, need to mirror logic in utils/keyboard_utils.py
        # Define groups: group_label -> { item_label: (token, tooltip) }
        placeholders = {
            "Date/Time": {
                "Date": ("{date}", "Insert date (YYYY-MM-DD)"),
                "Date (long)": ("{date_long}", "Insert long date (e.g. September 04, 2025)"),
                "Time": ("{time}", "Insert time (24hr, HH:MM)"),
                "Time (12hr)": ("{time_ampm}", "Insert time (12hr, e.g. 02:30 PM)"),
                "Date & Time": ("{datetime}", "Insert full datetime (YYYY-MM-DD HH:MM)"),
                "Weekday": ("{weekday}", "Insert weekday name (e.g. Thursday)"),
                "Month": ("{month}", "Insert month name (e.g. September)"),
                "Year": ("{year}", "Insert year (e.g. 2025)"),
            },
            "Context": {
                "Greeting": ("{greeting}", "Insert context-aware greeting (Good morning/afternoon/evening)"),
                "Location": ("{location}", "Insert configured location"),
            }
        }

        # Build submenus
        for group, items in placeholders.items():
            submenu = tools_menu.addMenu(group)
            for label, (token, tip) in items.items():
                act = QAction(label, self)
                act.setStatusTip(tip)
                act.triggered.connect(lambda checked=False, t=token: self.insert_token(t))
                submenu.addAction(act)

    # ----- HELPER FUNCTIONS -----

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