from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt


class SettingsCard(QWidget):
    def __init__(self, title: str, description: str, control: QWidget, parent=None):
        super().__init__(parent)

        self.title_text = title
        self.setObjectName("SettingsCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(75)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(16, 14, 16, 14)

        header = QHBoxLayout()
        header.addWidget(QLabel(title))
        header.setObjectName("SettingsCardTitle")
        header.addStretch()
        header.addWidget(control, alignment=Qt.AlignRight | Qt.AlignVCenter)

        desc = QLabel(description.strip())
        desc.setObjectName("SettingsCardDescription")
        desc.setWordWrap(True)

        root.addLayout(header)
        root.addWidget(desc)
