from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton
)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication, QCursor


class DynamicPlaceholderDialog(QDialog):
    """
    Prompts the user to fill in [[name]] placeholder values before a
    snippet is pasted. Shows every field at once in a single form
    ("single_form") or one at a time as a step-by-step wizard
    ("sequential"). Cancelling leaves self.values empty and rejects.
    """

    def __init__(self, names: list[str], mode: str = "single_form", parent=None):
        super().__init__(parent)
        self.names = list(names)
        self.mode = mode if mode == "sequential" else "single_form"
        self.values: dict[str, str] = {}
        self._index = 0
        self._fields: dict[str, QLineEdit] = {}

        self.setWindowTitle("Fill in Snippet Details")
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(420)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        # Build the UI based on the selected mode
        if self.mode == "sequential":
            self.build_sequential_ui()
        else:
            self.build_single_form_ui()
        self.applyStyles()

        shortcut = QShortcut(QKeySequence("Return"), self)
        shortcut.activated.connect(self.on_primary_action)

        # Center the dialog on the monitor where the mouse is located. Must run
        # after the UI is built and sized, otherwise self.rect() is still empty.
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos())
        if not screen:
            screen = QGuiApplication.primaryScreen()

        screen_center = screen.geometry().center()
        dialog_rect = self.rect()
        dialog_rect.moveCenter(screen_center)
        self.move(dialog_rect.topLeft())

    def build_single_form_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 24, 20)
        layout.setSpacing(14)

        self.title_label = QLabel("Fill in Snippet Details")
        self.title_label.setObjectName("VaultDialogTitle")
        layout.addWidget(self.title_label)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(6, 0, 0, 0)

        self.body_label = QLabel("This snippet has fields to fill in before pasting.")
        self.body_label.setObjectName("VaultDialogDesc")
        self.body_label.setWordWrap(True)

        body_layout.addWidget(self.body_label)
        layout.addLayout(body_layout)

        form = QFormLayout()
        form.setContentsMargins(6, 0, 0, 0)
        form.setSpacing(10)

        for name in self.names:
            field = QLineEdit()
            field.setObjectName("VaultField")
            self._fields[name] = field

            label = QLabel(name.title())
            label.setObjectName("VaultFieldLabel")
            form.addRow(label, field)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SnippetFormBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.primary_btn = QPushButton("Insert")
        self.primary_btn.setObjectName("VaultConfirmBtn")
        self.primary_btn.clicked.connect(self.on_primary_action)
        btn_row.addWidget(self.primary_btn)

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(8, 0, 0, 0)
        btn_layout.addLayout(btn_row)
        layout.addLayout(btn_layout)

        if self.names:
            self._fields[self.names[0]].setFocus()

    def build_sequential_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 24, 20)
        layout.setSpacing(14)

        self.title_label = QLabel("Fill in Snippet Details")
        self.title_label.setObjectName("VaultDialogTitle")
        layout.addWidget(self.title_label)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("VaultDialogDesc")
        layout.addWidget(self.progress_label)

        self.field_label = QLabel("")
        self.field_label.setObjectName("VaultFieldLabel")
        layout.addWidget(self.field_label)

        self.field = QLineEdit()
        self.field.setObjectName("VaultField")
        layout.addWidget(self.field)

        btn_row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("SnippetFormBtn")
        self.back_btn.clicked.connect(self.go_back)
        btn_row.addWidget(self.back_btn)
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SnippetFormBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        self.primary_btn = QPushButton("Next")
        self.primary_btn.setObjectName("VaultConfirmBtn")
        self.primary_btn.clicked.connect(self.on_primary_action)
        btn_row.addWidget(self.primary_btn)

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(8, 0, 0, 0)
        btn_layout.addLayout(btn_row)
        layout.addLayout(btn_layout)

        self.show_current_field()

    def show_current_field(self) -> None:
        total = len(self.names)
        name = self.names[self._index]
        self.progress_label.setText(f"Field {self._index + 1} of {total}")
        self.field_label.setText(name)
        self.field.setText(self.values.get(name, ""))
        self.back_btn.setEnabled(self._index > 0)
        self.primary_btn.setText("Finish" if self._index == total - 1 else "Next")
        self.field.setFocus()

    def go_back(self) -> None:
        if self._index == 0:
            return
        self.values[self.names[self._index]] = self.field.text()
        self._index -= 1
        self.show_current_field()

    def go_next(self) -> None:
        self.values[self.names[self._index]] = self.field.text()
        if self._index == len(self.names) - 1:
            self.accept()
            return
        self._index += 1
        self.show_current_field()

    def submit_single_form(self) -> None:
        for name, field in self._fields.items():
            self.values[name] = field.text()
        self.accept()

    def on_primary_action(self) -> None:
        if self.mode == "sequential":
            self.go_next()
        else:
            self.submit_single_form()

    def applyStyles(self) -> None:
        try:
            main = getattr(self.parent(), "parent", None)
            if main and hasattr(main, "medium_font_size"):
                mf = main.medium_font_size
                sf = main.small_font_size
                self.title_label.setFont(main.large_font_size_bold)
                for lbl in self.findChildren(QLabel, "VaultDialogDesc"):
                    lbl.setFont(sf)
                for lbl in self.findChildren(QLabel, "VaultFieldLabel"):
                    lbl.setFont(mf)
                for field in self.findChildren(QLineEdit, "VaultField"):
                    field.setFont(mf)
                for btn in self.findChildren(QPushButton):
                    btn.setFont(mf)
        except Exception:
            pass
