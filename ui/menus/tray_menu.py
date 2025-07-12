from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import Signal

class TrayMenu(QMenu):
    start_signal = Signal()     # Signal to start the service
    stop_signal = Signal()      # Signal to stop the service
    edit_signal = Signal()      # Signal to bring up UI
    exit_signal = Signal()      # Signal to exit app
    startup_signal = Signal(bool)

    def __init__(self, main=None, parent=None):
        super().__init__(parent)
        self.main = main
        self.parent = parent
        # Colors
        # Font Sizes
        self.add_actions()

    def add_actions(self):
        """ self.start_action = self.addAction("Start Service") #Define QIcon to set icon
        self.start_action.setData("Start Service")
        # Remember to set font
        self.start_action.triggered.connect(self.start_signal.emit)

        self.stop_action = self.addAction("Stop Service")
        self.stop_action.setData("Stop Service")
        self.stop_action.triggered.connect(self.stop_signal.emit)
        """

        # Launch at Startup (Checkbox style)
        self.launch_action = self.addAction("Launch at startup")
        self.launch_action.setData("Launch at startup")
        self.launch_action.setCheckable(True)  # Enable checkbox behavior
        self.launch_action.setChecked(True)  # Set initial state
        self.launch_action.toggled.connect(lambda checked: self.startup_signal.emit(checked))

        self.addSeparator() # Add seperator

        self.stop_action = self.addAction("Edit Snippets")
        self.stop_action.setData("Edit Snippets")
        self.stop_action.triggered.connect(self.edit_signal.emit)

        self.addSeparator() # Add seperator

        self.exit_action = self.addAction("Exit")
        self.exit_action.setData("Exit")
        self.exit_action.triggered.connect(self.exit_signal.emit)

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)
