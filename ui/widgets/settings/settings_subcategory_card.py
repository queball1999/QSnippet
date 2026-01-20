from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal


class SettingsSubCategoryCard(QWidget):
    clicked = Signal(str)

    def __init__(self, title: str, key: str, parent=None):
        super().__init__(parent)

        self.key = key
        self.setObjectName("SettingsSubCategoryCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(16, 14, 16, 14)

        text = QVBoxLayout()
        text.setObjectName("SettingsCardTitle")
        text.addWidget(QLabel(title))

        chevron = QLabel("›")
        chevron.setObjectName("SettingsChevron")
        chevron.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        root.addLayout(text)
        root.addStretch()
        root.addWidget(chevron)

    def mousePressEvent(self, event):
        """ Emit signal on click """
        self.clicked.emit(self.key)
