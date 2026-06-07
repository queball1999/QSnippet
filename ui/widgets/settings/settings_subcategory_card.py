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
        self.setCursor(Qt.PointingHandCursor)

        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(16, 14, 16, 14)

        text_container = QWidget()
        text_container.setMinimumWidth(300)
        text_container.setStyleSheet("background-color: transparent;")

        text = QVBoxLayout(text_container)
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("SettingsCardTitle")
        title_label.setStyleSheet("background-color: transparent;")
        self.apply_font_to_label(title_label, "medium")
        text.addWidget(title_label)

        if description:
            desc_label = QLabel(description.strip())
            desc_label.setObjectName("SettingsCardDescription")
            desc_label.setStyleSheet("background-color: transparent;")
            desc_label.setWordWrap(True)
            self.apply_font_to_label(desc_label, "small")
            text.addWidget(desc_label)

        chevron = QLabel("›")
        chevron.setObjectName("SettingsChevron")
        chevron.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.apply_font_to_label(chevron, "large")

        root.addWidget(text_container, 1)
        root.addStretch()
        root.addWidget(chevron)

    def apply_font_to_label(self, label: QLabel, font_size: str):
        """Apply font to label from main app if available."""
        try:
            # Navigate to main app: card -> page -> dialog -> window -> app
            widget = self.parent()
            while widget and not hasattr(widget, 'parent'):
                widget = widget.parent()

            if widget and hasattr(widget, 'parent'):
                window = widget.parent()
                if hasattr(window, 'parent'):
                    app = window.parent()
                    # Keep sub-category title/description typography aligned with
                    # main settings cards.
                    if label.objectName() == "SettingsCardTitle" and hasattr(app, "medium_font_size_bold"):
                        label.setFont(getattr(app, "medium_font_size_bold"))
                        return

                    font_attr = f"{font_size}_font_size"
                    if hasattr(app, font_attr):
                        font = getattr(app, font_attr)
                        label.setFont(font)
        except Exception:
            pass

    def mousePressEvent(self, event):
        """ Emit signal on click """
        self.clicked.emit(self.key)
