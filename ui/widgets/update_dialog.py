"""
The "update available" dialog.

A real QDialog, not a QMessageBox with detailed text: QMessageBox lays out
its details pane through private code that can't be made to resize or fit
flush against the buttons, so release notes get a purpose-built window.

Notes render as markdown with a heading size ramp, the notes pane stretches
and the dialog resizes, and buttons stay pinned to the bottom.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontInfo, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStyle,
    QTextBrowser, QVBoxLayout,
)

logger = logging.getLogger(__name__)

# Size ramp for markdown headings, relative to the view's own font: Qt
# bolds heading blocks but leaves point size unset, so they'd render at
# body size otherwise. Deliberately gentle.
HEADING_SCALE = {1: 1.45, 2: 1.30, 3: 1.18, 4: 1.10, 5: 1.05, 6: 1.0}

COLLAPSED_WIDTH = 520
EXPANDED_HEIGHT = 520
NOTES_MIN_HEIGHT = 260


class UpdateAvailableDialog(QDialog):
    """
    Offers an available update and shows what changed.

    Updates are never forced, so this is a plain question with a real decline
    answer. exec() returns QDialog.Accepted only when the user chooses to
    update.
    """

    def __init__(self, info, parent=None):
        super().__init__(parent)

        self.info = info
        self.notes_visible = False

        self.setWindowTitle("Update available")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.setMinimumWidth(COLLAPSED_WIDTH)

        if parent is not None:
            # Inherit the already-resolved application icon.
            self.setWindowIcon(parent.windowIcon())

        self.build_ui()
        self.applyStyles()

        # Size to the collapsed layout before the notes pane is revealed.
        self.adjustSize()

    # ----- construction -----

    def build_ui(self) -> None:
        """
        Lay the dialog out.

        Order matters: header, then the notes pane that absorbs spare height,
        then the buttons pinned to the bottom. With the buttons last there is
        no gap between them and the notes to tune away.

        Returns:
            None
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        layout.addLayout(self.build_header())

        self.notes_view = self.build_notes_view()
        layout.addWidget(self.notes_view, 1)

        layout.addLayout(self.build_buttons())

    def build_header(self) -> QHBoxLayout:
        """Build the icon and heading block."""
        header = QHBoxLayout()
        header.setSpacing(14)

        icon_label = QLabel()
        icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setFixedSize(48, 48)
        header.addWidget(icon_label, 0, Qt.AlignTop)

        text_block = QVBoxLayout()
        text_block.setSpacing(4)

        title = QLabel(f"QSnippet {self.info.latest_version} is available.")
        # Named role, not an ad-hoc setFont(): ThemeManager's font sweep
        # resets any unregistered QLabel to plain "medium". See applyStyles()
        # below and OBJECT_NAME_FONTS in ui/theme_manager.py.
        title.setObjectName("UpdateDialogTitle")
        title.setWordWrap(True)

        subtitle = QLabel(f"You are running {self.info.current_version}.")
        subtitle.setWordWrap(True)

        text_block.addWidget(title)
        text_block.addWidget(subtitle)
        text_block.addStretch(1)

        header.addLayout(text_block, 1)
        return header

    def build_notes_view(self) -> QTextBrowser:
        """Build the release notes pane, hidden until the user asks for it."""
        view = QTextBrowser()
        view.setObjectName("UpdateNotesView")
        view.setOpenExternalLinks(True)
        view.setMinimumHeight(NOTES_MIN_HEIGHT)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        view.setLineWrapMode(QTextBrowser.WidgetWidth)
        view.hide()

        notes = getattr(self.info, "notes", "") or ""
        if notes:
            view.setMarkdown(notes)
            self.style_headings(view)

        return view

    def build_buttons(self) -> QHBoxLayout:
        """Build the button row."""
        row = QHBoxLayout()
        row.setSpacing(8)

        self.details_button = QPushButton("Show Details")
        self.details_button.clicked.connect(self.toggle_notes)
        self.details_button.setEnabled(bool(getattr(self.info, "notes", "")))
        row.addWidget(self.details_button)

        row.addStretch(1)

        self.update_button = QPushButton("Update now")
        self.update_button.setDefault(True)
        self.update_button.clicked.connect(self.accept)
        row.addWidget(self.update_button)

        self.later_button = QPushButton("Not now")
        self.later_button.clicked.connect(self.reject)
        row.addWidget(self.later_button)

        return row

    def applyStyles(self) -> None:
        """
        Apply role-based fonts to every named widget in this dialog.

        Called once after construction, and again by ThemeManager's repaint
        sweep (by name, on every open widget) whenever theme/accent/scale
        changes reset labels to the plain "medium" font - without this hook
        the title would flash back to that default while the dialog is open.

        Returns:
            None
        """
        from ui.theme_manager import ThemeManager

        ThemeManager.apply_fonts(self)

    # ----- behaviour -----

    def toggle_notes(self) -> None:
        """
        Show or hide the release notes pane, resizing the dialog to match.

        Returns:
            None
        """
        self.notes_visible = not self.notes_visible

        self.notes_view.setVisible(self.notes_visible)
        self.details_button.setText(
            "Hide Details" if self.notes_visible else "Show Details"
        )

        if self.notes_visible:
            self.resize(max(self.width(), COLLAPSED_WIDTH), EXPANDED_HEIGHT)
        else:
            # adjustSize alone won't shrink an already-enlarged window, so
            # clear the height floor first.
            self.setMinimumHeight(0)
            self.adjustSize()

    def style_headings(self, view: QTextBrowser) -> None:
        """
        Give markdown headings a visible size step.

        Qt bolds headings but leaves point size unset, so they'd render at
        body size otherwise. The ramp is relative to the view's own font.

        Args:
            view (QTextBrowser): The rendered markdown view to restyle.

        Returns:
            None
        """
        base = view.font().pointSizeF()
        if base <= 0:
            base = QFontInfo(view.font()).pointSizeF()
        if base <= 0:
            logger.debug("Could not determine a base font size for the notes view")
            return

        document = view.document()
        cursor = QTextCursor(document)
        block = document.firstBlock()

        while block.isValid():
            level = block.blockFormat().headingLevel()

            if level:
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

                fmt = QTextCharFormat()
                fmt.setFontPointSize(base * HEADING_SCALE.get(level, 1.0))
                fmt.setFontWeight(QFont.Bold)
                cursor.mergeCharFormat(fmt)

            block = block.next()
