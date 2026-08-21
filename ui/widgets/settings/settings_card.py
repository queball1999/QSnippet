from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy, QPushButton
from PySide6.QtCore import Qt


class SettingsCard(QWidget):
    def __init__(self, title: str, description: str, control: QWidget, reset_btn: QPushButton = None, parent=None):
        super().__init__(parent)

        self.title_text = title
        self.setObjectName("SettingsCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(8, 14, 16, 14)

        title_label = QLabel(title)
        title_label.setObjectName("SettingsCardTitle")
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        control.setMinimumWidth(100)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(title_label, 1)
        if reset_btn:
            header.addWidget(reset_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(control, alignment=Qt.AlignRight | Qt.AlignVCenter)

        desc = QLabel(description.strip())
        desc.setObjectName("SettingsCardDescription")
        desc.setWordWrap(True)

        root.addLayout(header)
        root.addWidget(desc)

        self.applyStyles()

    def applyStyles(self) -> None:
        """
        Re-apply role-correct fonts to the card.

        Sizing comes from ThemeManager.OBJECT_NAME_FONTS via the labels'
        object names, so the card matches what SettingsDialog and the QSS
        rules assume for SettingsCardTitle / SettingsCardDescription.
        """
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_fonts(self)
