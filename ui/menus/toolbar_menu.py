from PySide6.QtWidgets import QToolBar
from PySide6.QtGui import QIcon, QAction


class ToolbarMenu(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.parent = parent
        self.init_actions()

    def init_actions(self):
        self.editor = self.parent.editor

        home_icon = QIcon.fromTheme("go-home")  # or your own .png
        home_action = QAction(home_icon, "Home", self)
        home_action.setToolTip("Home")
        home_action.triggered.connect(self.editor.show_home_widget)
        self.addAction(home_action)

        # --- New Snippet ---
        new_icon = QIcon.fromTheme("document-new")  # or your own .png
        new_action = QAction(new_icon, "New Snippet", self)
        new_action.setToolTip("New Snippet (ctrl+n)")
        new_action.triggered.connect(self.editor.show_new_form)
        self.addAction(new_action)

        # --- Save Snippet ---
        save_icon = QIcon.fromTheme("document-save")
        save_action = QAction(save_icon, "Save Snippet", self)
        save_action.setToolTip("Save Snippet (ctrl+s)")
        save_action.triggered.connect(self.editor.on_save)
        self.addAction(save_action)

        # --- Delete Snippet ---
        del_icon = QIcon.fromTheme("edit-delete")
        delete_action = QAction(del_icon, "Delete Snippet", self)
        delete_action.setToolTip("Delete Snippet (del)")
        delete_action.triggered.connect(self.editor.on_delete)
        self.addAction(delete_action)

        # You can add more toolbar buttons here…
