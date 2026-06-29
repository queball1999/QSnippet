from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut


class SnippetPopoutDialog(QDialog):
    snippetApplied = Signal(str)

    def __init__(self, snippet_text: str = "", snippet_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Snippet")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(500, 350)
        self.resize(700, 500)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowMinimizeButtonHint
        )
        self.build_ui(snippet_text, snippet_name)
        self.applyStyles()

    def build_ui(self, snippet_text: str, snippet_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.snippet = QLabel(snippet_name if snippet_name else "Snippet")
        self.snippet.setObjectName("PopoutSnippetName")
        layout.addWidget(self.snippet)

        self.label = QLabel("Edit your snippet below:")
        self.label.setObjectName("PopoutLabel")
        layout.addWidget(self.label)

        self.editor = QTextEdit()
        self.editor.setObjectName("PopoutEditor")
        self.editor.setPlainText(snippet_text)
        self.editor.setPlaceholderText("Enter your snippet text here...")
        layout.addWidget(self.editor)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.setToolTip("Apply changes and close (Ctrl+Enter)")
        self.close_btn.setObjectName("SnippetFormBtn")
        self.close_btn.clicked.connect(self.apply_and_close)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.apply_and_close)

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

    def applyStyles(self) -> None:
        try:
            main = getattr(self.parent(), 'parent', None)
            if main and hasattr(main, 'medium_font_size'):
                self.snippet.setFont(main.large_font_size_bold)
                self.label.setFont(main.medium_font_size)
                self.editor.setFont(main.medium_font_size)
                self.close_btn.setFont(main.medium_font_size)
        except Exception:
            pass

    def apply_and_close(self) -> None:
        self.snippetApplied.emit(self.editor.toPlainText())
        self.close()
