from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import Signal

class TrayMenu(QMenu):
    start_signal = Signal()     # Signal to start the service
    stop_signal = Signal()      # Signal to stop the service
    edit_signal = Signal()      # Signal to bring up UI
    quit_signal = Signal()      # Signal to quit app

    def __init__(self, parent=None):
        super().__init__(parent)
        # Colors
        # Font Sizes
        self.add_actions()

    def add_actions(self):
        self.start_action = self.addAction("Start Service") #Define QIcon to set icon
        self.start_action.setData("Start Service")
        # Remember to set font
        self.start_action.triggered.connect(self.start_signal.emit)

        self.stop_action = self.addAction("Stop Service")
        self.stop_action.setData("Stop Service")
        self.stop_action.triggered.connect(self.stop_signal.emit)

        self.addSeparator() # Add seperator

        self.stop_action = self.addAction("Edit Snippets")
        self.stop_action.setData("Edit Snippets")
        self.stop_action.triggered.connect(self.edit_signal.emit)

        self.addSeparator() # Add seperator

        self.quit_action = self.addAction("Quit")
        self.quit_action.setData("Quit")
        self.quit_action.triggered.connect(self.quit_signal.emit)

    def update_stylesheet(self):
        """ This function handles updating the stylesheet. """
        #self.setStyleSheet(f""" """)
