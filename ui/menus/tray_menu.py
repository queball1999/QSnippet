from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Signal

class TrayMenu(QMenu):
    """
    TrayMenu is the context menu for the system tray icon, allowing users 
    to edit quick settings, open UI, and exit the application.
    """
    # Primary Signals
    edit_signal = Signal()      # Signal to bring up UI
    exit_signal = Signal()      # Signal to exit app

    # Quick Settings Signals
    startup_signal = Signal(bool)   # Signal to toggle startup option
    showui_signal = Signal(bool)    # Signal to toggle show UI at start option

    def __init__(self, main=None, parent=None):
        """
        Initialize the TrayMenu with system tray actions.

        Args:
            main (Any): Reference to the main application object.
            parent (QWidget): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.main = main
        self.parent = parent
        # Colors
        # Font Sizes
        self.add_actions()

    def add_actions(self):
        """
        Add all actions to the tray menu.

        Configures startup behavior, UI display options, and application control
        actions with appropriate signals and checkable states.

        Returns:
            None
        """
        # Launch at Startup (Checkbox style)
        self.launch_action = self.addAction("Launch at boot")
        self.launch_action.setData("Launch at boot")
        self.launch_action.setCheckable(True)
        self.launch_action.setChecked(
            self.main.settings["general"]["startup_behavior"]["start_at_boot"].get("value", False)
        )
        self.launch_action.toggled.connect(lambda checked: self.startup_signal.emit(checked))

        # Show UI at Start (Checkbox style)
        self.showui_action = self.addAction("Show UI at start")
        self.showui_action.setData("Show UI at start")
        self.showui_action.setCheckable(True)
        self.showui_action.setChecked(
            self.main.settings["general"]["startup_behavior"]["show_ui_at_start"].get("value", False)
        )
        self.showui_action.toggled.connect(lambda checked: self.showui_signal.emit(checked))

        self.addSeparator() # Add seperator

        self.stop_action = self.addAction("Edit Snippets")
        self.stop_action.setData("Edit Snippets")
        self.stop_action.triggered.connect(self.edit_signal.emit)

        self.addSeparator() # Add seperator

        self.exit_action = self.addAction("Exit")
        self.exit_action.setData("Exit")
        self.exit_action.triggered.connect(self.exit_signal.emit)

    def update_stylesheet(self):
        """
        Apply the CSS stylesheet to tray menu components.

        Updates styling rules for the tray menu and its items.

        Returns:
            None
        """
        #self.setStyleSheet(f""" """)
