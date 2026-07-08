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
        self.apply_font_to_label(title_label, "small")

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
        self.apply_font_to_label(desc, "small")

        root.addLayout(header)
        root.addWidget(desc)

    def apply_font_to_label(self, label: QLabel, font_size: str):
        """Apply font to label from main app if available."""
        try:
            # Navigate to main app: card -> page/subcategory -> dialog -> window -> app
            widget = self.parent()
            while widget and not hasattr(widget, 'parent'):
                widget = widget.parent()

            if widget and hasattr(widget, 'parent'):
                window = widget.parent()
                if hasattr(window, 'parent'):
                    app = window.parent()
                    font_attr = f"{font_size}_font_size"
                    if hasattr(app, font_attr):
                        font = getattr(app, font_attr)
                        label.setFont(font)
        except Exception:
            pass
