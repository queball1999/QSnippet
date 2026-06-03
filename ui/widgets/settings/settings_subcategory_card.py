from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal


class SettingsSubCategoryCard(QWidget):
    clicked = Signal(str)

    def __init__(self, title: str, key: str, description: str = "", parent=None):
        super().__init__(parent)

        self.key = key
        self.setObjectName("SettingsSubCategoryCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(16, 14, 16, 14)

        text_container = QWidget()
        text_container.setMinimumWidth(300)
        text_container.setStyleSheet("background-color: transparent;")

        text = QVBoxLayout(text_container)
        text.setObjectName("SettingsCardTitle")
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("background-color: transparent;")
        text.addWidget(title_label)

        if description:
            desc_label = QLabel(description.strip())
            desc_label.setObjectName("SettingsCardDescription")
            desc_label.setStyleSheet("background-color: transparent;")
            desc_label.setWordWrap(True)
            text.addWidget(desc_label)

        chevron = QLabel("›")
        chevron.setObjectName("SettingsChevron")
        chevron.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        root.addWidget(text_container, 1)
        root.addStretch()
        root.addWidget(chevron)

    def mousePressEvent(self, event):
        """ Emit signal on click """
        self.clicked.emit(self.key)
