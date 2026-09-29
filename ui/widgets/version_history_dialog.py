import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal

from ui.widgets.AppMessageBox import AppMessageBox
from utils.snippet_db import DatabaseOperationError

logger = logging.getLogger(__name__)

COL_EDITED, COL_LABEL, COL_TRIGGER, COL_PREVIEW = range(4)


def preview_text(entry: dict) -> str:
    """Return a short single-line preview of a history entry's content."""
    if entry.get("is_encrypted"):
        return "(Encrypted)"
    text = (entry.get("snippet") or "").replace("\n", " ").strip()
    if len(text) > 80:
        text = text[:80] + "..."
    return text


def format_edited_at(raw: str) -> str:
    """Render a stored UTC timestamp in local time, falling back to the raw string."""
    try:
        return datetime.fromisoformat(raw).astimezone().strftime("%d %b %Y, %H:%M:%S")
    except Exception:
        return raw or "Unknown date"


class VersionHistoryDialog(QDialog):
    """
    Shows saved prior snippet versions and lets the user restore one.

    Pass an entry dict to scope the dialog to that one snippet, or None
    to browse saved versions across every snippet.
    """

    restored = Signal(dict)   # the restored, now-current entry

    def __init__(
        self,
        entry: dict | None,
        snippet_db,
        history_enabled=True,
        history_limit=10,
        message_box=None,
        unsaved_snippet_id=None,
        parent=None,
    ):
        """
        Initialize the VersionHistoryDialog.

        Args:
            entry (dict | None): The snippet entry to show history for, or
                None to browse saved versions across every snippet.
            snippet_db: SnippetDB instance for reading/restoring history.
            history_enabled (bool): Whether restoring itself should be
                captured as a new history entry, per current settings.
            history_limit (int): Max history rows to retain per snippet
                after a restore, per current settings.
            message_box (AppMessageBox | None): The app's shared message box,
                so prompts carry the app icon and styling.
            unsaved_snippet_id (int | None): Id of the snippet open in the
                form with unsaved edits, so restoring it can warn first.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.entry = entry
        self.snippet_db = snippet_db
        self.history_enabled = history_enabled
        self.history_limit = history_limit
        self.message_box = message_box or AppMessageBox(parent=self)
        self.unsaved_snippet_id = unsaved_snippet_id

        if entry is None:
            self.setWindowTitle("Snippet Version History")
        else:
            self.setWindowTitle(f'Version History - {entry.get("label", "")}')
        self.resize(760, 480)
        self.setMinimumSize(560, 360)

        self.build_ui()
        self.load_history()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        if self.entry is None:
            header_text = "Saved versions across all snippets"
            empty_text = "No saved versions yet.\nVersions are saved automatically each time a snippet is edited or renamed."
        else:
            header_text = f'Saved versions of "{self.entry.get("label", "")}" ({self.entry.get("trigger", "")})'
            empty_text = "No saved versions yet.\nVersions are saved automatically each time you edit or rename this snippet."

        header_col = QVBoxLayout()
        header_col.setSpacing(2)

        header = QLabel(header_text)
        header.setObjectName("PanelTitle")
        header_col.addWidget(header)

        if not self.history_enabled:
            hint_text = "Version history is turned off. Existing versions can still be restored."
        elif self.history_limit > 0:
            hint_text = f"Keeping up to {self.history_limit} versions per snippet. Select a version and click Restore."
        else:
            hint_text = "Keeping unlimited versions per snippet. Select a version and click Restore."
        hint = QLabel(hint_text)
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        header_col.addWidget(hint)

        root.addLayout(header_col)

        self.empty_label = QLabel(empty_text)
        self.empty_label.setObjectName("FieldHint")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        root.addWidget(self.empty_label, 1)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("VersionHistoryTable")
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderLabels(["Edited", "Label", "Trigger", "Snippet"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(COL_EDITED, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_LABEL, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_TRIGGER, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_PREVIEW, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        root.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.restore_btn = QPushButton("Restore")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.on_restore_clicked)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_row.addWidget(self.restore_btn)
        button_row.addWidget(close_btn)
        root.addLayout(button_row)

    def load_history(self):
        """Fetch and render saved versions for this snippet, or for all snippets."""
        try:
            if self.entry is None:
                rows = self.snippet_db.get_all_snippet_history()
            else:
                rows = self.snippet_db.get_snippet_history(self.entry["id"])
        except DatabaseOperationError as exc:
            logger.exception("Failed to load snippet history")
            self.message_box.warning(f"Failed to load version history: {exc}", title="Version History")
            rows = []

        self.table.setRowCount(0)
        self.empty_label.setVisible(not rows)
        self.table.setVisible(bool(rows))

        for history_entry in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)

            edited_item = QTableWidgetItem(format_edited_at(history_entry.get("edited_at", "")))
            edited_item.setData(Qt.UserRole, {
                "history_id": history_entry["id"],
                "snippet_id": history_entry["snippet_id"],
            })
            label_item = QTableWidgetItem(history_entry.get("label", ""))
            trigger_item = QTableWidgetItem(history_entry.get("trigger", ""))
            preview_item = QTableWidgetItem(preview_text(history_entry))
            preview_item.setToolTip(history_entry.get("snippet", "") if not history_entry.get("is_encrypted") else "")

            for item in (edited_item, label_item, trigger_item, preview_item):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(row, COL_EDITED, edited_item)
            self.table.setItem(row, COL_LABEL, label_item)
            self.table.setItem(row, COL_TRIGGER, trigger_item)
            self.table.setItem(row, COL_PREVIEW, preview_item)

        self.restore_btn.setEnabled(False)

    def selected_history(self):
        """Return {"history_id", "snippet_id"} for the selected row, or None."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, COL_EDITED)
        return item.data(Qt.UserRole) if item else None

    def on_selection_changed(self):
        self.restore_btn.setEnabled(self.selected_history() is not None)

    def on_restore_clicked(self):
        selected = self.selected_history()
        if selected is None:
            return

        message = "Restore the snippet to this earlier version?"
        if self.history_enabled:
            message += "\n\nThe current version will be saved to history first."
        if selected["snippet_id"] == self.unsaved_snippet_id:
            message += (
                "\n\nThis snippet has unsaved edits in the form. "
                "Restoring will discard them."
            )
        reply = self.message_box.question(message, title="Restore This Version")
        if reply != QMessageBox.Yes:
            return

        try:
            self.snippet_db.restore_snippet_version(
                selected["history_id"],
                history_enabled=self.history_enabled,
                history_limit=self.history_limit,
            )
        except DatabaseOperationError as exc:
            self.message_box.warning(str(exc), title="Restore Failed")
            return

        if selected["snippet_id"] == self.unsaved_snippet_id:
            self.unsaved_snippet_id = None  # The form is reloaded on restore

        restored_entry = self.snippet_db.get_snippet(selected["snippet_id"])
        if self.entry is not None:
            self.entry = restored_entry
        self.load_history()
        self.restored.emit(restored_entry)
