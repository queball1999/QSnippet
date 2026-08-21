import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QIcon, QDesktopServices

from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)

PAGE_SIZE_OPTIONS = [10, 25, 50, 100]
DEFAULT_PAGE_SIZE = 10

# Column layout: (title, initial width). The actions column is sized to its
# buttons and pinned; every other column is user-resizable.
COLUMNS = [
    ("Date", 190),
    ("Contents", 180),
    ("Location", 320),
    ("", 108),
]
COL_DATE, COL_CONTENTS, COL_LOCATION, COL_ACTIONS = range(4)


class BackupSettingsPage(QWidget):
    """
    Backup history and management, shown inside the main settings dialog.

    QSnippet copies the database and exports a YAML snapshot before any
    migration that will modify existing data, bundling both into a single zip
    in the backups folder. This page lists those backups in a paginated table
    and lets the user take one on demand.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.page_size = DEFAULT_PAGE_SIZE
        self.page = 0
        self.entries: list[dict] = []
        self.page_buttons: list[QWidget] = []
        self.pager_visible = False

        self.build_ui()
        self.refresh_state()
        self.applyStyles()

    # ----- Icons -----

    def themed_icon(self, name: str) -> QIcon:
        """Load an icon tinted for the active theme."""
        icon = QIcon(FileUtils.icon_path(name))
        try:
            from ui.theme_manager import ThemeManager
            tm = ThemeManager.get_instance()
            if tm:
                icon = tm.recolor_icon(icon, tm.icon_color())
        except Exception:
            pass
        return icon

    # ----- UI -----

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.header = QLabel("Backups")
        self.header.setObjectName("SettingsHeader")
        layout.addWidget(self.header)

        # Body content is inset to match the margin SettingsCard applies on
        # dynamically generated pages.
        content = QVBoxLayout()
        content.setContentsMargins(8, 0, 0, 0)
        content.setSpacing(12)
        layout.addLayout(content)

        desc = QLabel(
            "Before an update changes how snippets are stored, QSnippet copies the "
            "database and exports a YAML snapshot of your snippets, bundled together "
            "as a single zip in the backups folder.\n\n"
            "Backups are never deleted automatically; remove old files yourself once "
            "you no longer need them."
        )
        desc.setObjectName("SettingsCardDescription")
        desc.setWordWrap(True)
        content.addWidget(desc)

        content.addLayout(self.build_actions_row())

        self.status_label = QLabel("")
        self.status_label.setObjectName("SettingsCardDescription")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        content.addWidget(self.status_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("VaultSeparator")
        content.addWidget(sep)

        self.history_header = QLabel("History")
        self.history_header.setObjectName("SettingsCardTitle")
        content.addWidget(self.history_header)

        self.empty_label = QLabel("No backups have been made yet.")
        self.empty_label.setObjectName("SettingsCardDescription")
        self.empty_label.setWordWrap(True)
        content.addWidget(self.empty_label)

        content.addWidget(self.build_table())
        content.addLayout(self.build_pagination_row())

        content.addStretch()
        scroll.setWidget(inner)

    def build_actions_row(self) -> QHBoxLayout:
        """Management actions that apply to backups as a whole."""
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.backup_now_btn = QPushButton("Back Up Now")
        self.backup_now_btn.setObjectName("VaultConfirmBtn")
        self.backup_now_btn.setCursor(Qt.PointingHandCursor)
        self.backup_now_btn.setToolTip(
            "Copy the database and export a YAML snapshot right now"
        )
        self.backup_now_btn.clicked.connect(self.on_backup_now)
        actions.addWidget(self.backup_now_btn)

        self.open_folder_btn = QPushButton("Open Backup Folder")
        self.open_folder_btn.setObjectName("SnippetFormBtn")
        self.open_folder_btn.setCursor(Qt.PointingHandCursor)
        self.open_folder_btn.clicked.connect(self.on_open_folder)
        actions.addWidget(self.open_folder_btn)

        actions.addStretch()
        return actions

    def build_table(self) -> QTableWidget:
        """Backup history table: truncated cells, tooltips, resizable columns."""
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("BackupHistoryTable")
        self.table.setHorizontalHeaderLabels([title for title, _ in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        # Long paths are truncated with an ellipsis; the full value lives in
        # the tooltip, so a narrow column never hides information.
        self.table.setTextElideMode(Qt.ElideRight)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for index, (_, width) in enumerate(COLUMNS):
            if index == COL_ACTIONS:
                # Pinned: holds fixed-size icon buttons, nothing to resize.
                header.setSectionResizeMode(index, QHeaderView.Fixed)
            else:
                header.setSectionResizeMode(index, QHeaderView.Interactive)
            self.table.setColumnWidth(index, width)

        return self.table

    def build_pagination_row(self) -> QHBoxLayout:
        """Page-size selector on the left, page navigation on the right."""
        row = QHBoxLayout()
        row.setSpacing(8)

        self.page_size_label = QLabel("Rows per page")
        self.page_size_label.setObjectName("SettingsCardDescription")
        row.addWidget(self.page_size_label)

        self.page_size_combo = QComboBox()
        self.page_size_combo.setObjectName("BackupPageSize")
        self.page_size_combo.addItems([str(n) for n in PAGE_SIZE_OPTIONS])
        self.page_size_combo.setCurrentText(str(DEFAULT_PAGE_SIZE))
        self.page_size_combo.setFixedWidth(90)
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        row.addWidget(self.page_size_combo)

        self.range_label = QLabel("")
        self.range_label.setObjectName("SettingsCardDescription")
        row.addWidget(self.range_label)

        row.addStretch()

        self.back_btn = QPushButton(" Back")
        self.back_btn.setObjectName("SnippetFormBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setToolTip("Previous page")
        self.back_btn.clicked.connect(lambda: self.go_to_page(self.page - 1))
        row.addWidget(self.back_btn)

        # Numbered page buttons are rebuilt on every render
        self.page_button_row = QHBoxLayout()
        self.page_button_row.setSpacing(4)
        row.addLayout(self.page_button_row)

        self.next_btn = QPushButton("Next ")
        self.next_btn.setObjectName("SnippetFormBtn")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setToolTip("Next page")
        self.next_btn.clicked.connect(lambda: self.go_to_page(self.page + 1))
        row.addWidget(self.next_btn)

        self.pagination_row = row
        return row

    # ----- Data -----

    def history(self) -> list:
        """Recorded backups, newest first."""
        try:
            entries = (
                self.window.parent.settings.get("backups", {})
                .get("database_backups", {})
                .get("value", [])
            )
            return list(reversed(entries or []))
        except Exception:
            logger.exception("Could not read backup history")
            return []

    def page_count(self) -> int:
        if not self.entries:
            return 1
        return max(1, -(-len(self.entries) // self.page_size))

    def refresh_state(self) -> None:
        """Reload the history and re-render the current page."""
        self.entries = self.history()
        self.page = min(self.page, self.page_count() - 1)
        self.render_page()

    # ----- Rendering -----

    def render_page(self) -> None:
        """Fill the table with the current page and refresh the pager."""
        has_entries = bool(self.entries)
        self.empty_label.setVisible(not has_entries)
        self.table.setVisible(has_entries)
        self.set_pagination_visible(has_entries)

        start = self.page * self.page_size
        rows = self.entries[start:start + self.page_size]

        self.table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            self.fill_row(row, entry)

        self.table.resizeRowsToContents()
        self.render_pagination()
        self.applyStyles()

    def fill_row(self, row: int, entry: dict) -> None:
        """Populate one table row, tooltipping the untruncated value."""
        raw_timestamp = entry.get("timestamp", "")
        self.set_cell(row, COL_DATE, self.format_timestamp(raw_timestamp),
                      tooltip=raw_timestamp or "Unknown date")

        self.set_cell(row, COL_CONTENTS, self.describe_contents(entry),
                      tooltip=self.contents_tooltip(entry))

        location = self.location_of(entry)
        self.set_cell(row, COL_LOCATION, location, tooltip=location or "Unknown location")

        self.table.setCellWidget(row, COL_ACTIONS, self.build_row_actions(entry))

    def set_cell(self, row: int, column: int, text: str, tooltip: str) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(tooltip)
        item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, column, item)

    def build_row_actions(self, entry: dict) -> QWidget:
        """Inline icon buttons for the files this backup produced."""
        container = QWidget()
        container.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        # Archive replaces the loose pair, so only one of these applies to a
        # given entry; older entries recorded before archiving still have both.
        specs = [
            (entry.get("archive_path"), "folder-zip-outline.svg", "Show backup archive"),
            (entry.get("db_backup_path"), "database-outline.svg", "Show database copy"),
            (entry.get("export_path"), "file-document-outline.svg", "Show snippet export"),
        ]
        for path, icon_name, tip in specs:
            if path:
                layout.addWidget(self.icon_button(icon_name, tip, path))

        folder = self.location_of(entry)
        if folder:
            layout.addWidget(
                self.icon_button("folder-open-outline.svg", "Open containing folder",
                                 folder, reveal=False)
            )

        layout.addStretch()
        return container

    def icon_button(self, icon_name: str, tooltip: str, path: str,
                    reveal: bool = True) -> QPushButton:
        """
        One inline action button.

        Disabled rather than hidden when the file is gone, so the row still
        shows what the backup was supposed to contain.
        """
        btn = QPushButton()
        btn.setObjectName("BackupRowBtn")
        # Recorded so applyStyles can re-tint the baked pixmap on theme change
        btn.setProperty("iconName", icon_name)
        btn.setIcon(self.themed_icon(icon_name))
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFlat(True)

        exists = bool(path) and Path(path).exists()
        btn.setEnabled(exists)
        if exists:
            btn.setToolTip(f"{tooltip}\n{path}")
            if reveal:
                btn.clicked.connect(lambda checked=False, p=str(path): self.reveal(p))
            else:
                btn.clicked.connect(lambda checked=False, p=str(path): self.open_path(p))
        else:
            btn.setToolTip(f"{tooltip}\nFile no longer exists:\n{path}")

        return btn

    # ----- Pagination -----

    def set_pagination_visible(self, visible: bool) -> None:
        """
        Show or hide the pager as a whole.

        Tracked on self.pager_visible rather than read back from isVisible():
        every child of a page that has not been shown yet reports False, so
        querying Qt here would suppress the page numbers on first render.
        """
        self.pager_visible = visible
        for widget in (self.page_size_label, self.page_size_combo, self.range_label,
                       self.back_btn, self.next_btn):
            widget.setVisible(visible)
        if not visible:
            self.clear_page_buttons()

    def clear_page_buttons(self) -> None:
        for btn in self.page_buttons:
            self.page_button_row.removeWidget(btn)
            btn.deleteLater()
        self.page_buttons.clear()

    def page_number_sequence(self, current: int, total: int, window: int = 3) -> list:
        """
        Page numbers to display, with None marking an elided gap.

        Always includes the first and last page plus a window around the
        current one, so navigation reads "1 2 3 ... 10" rather than listing
        every page.
        """
        if total <= window + 2:
            return list(range(total))

        # Clamp the window inside the range so a full run of consecutive
        # numbers always shows, giving "1 2 3 ... 10" at the start rather than
        # the lopsided "1 2 ... 10" a naive current +/- offset produces.
        half = window // 2
        first = max(0, min(current - half, total - window))
        pages = {0, total - 1} | set(range(first, first + window))

        ordered = sorted(pages)
        sequence = []
        previous = None
        for page in ordered:
            if previous is not None and page - previous > 1:
                sequence.append(None)
            sequence.append(page)
            previous = page
        return sequence

    def render_pagination(self) -> None:
        """Rebuild the numbered page buttons and the range summary."""
        self.clear_page_buttons()

        total_pages = self.page_count()
        total_entries = len(self.entries)

        if total_entries:
            start = self.page * self.page_size + 1
            end = min(start + self.page_size - 1, total_entries)
            self.range_label.setText(f"{start}-{end} of {total_entries}")
        else:
            self.range_label.setText("")

        self.back_btn.setEnabled(self.page > 0)
        self.next_btn.setEnabled(self.page < total_pages - 1)
        self.back_btn.setIcon(self.themed_icon("chevron-left.svg"))
        self.next_btn.setIcon(self.themed_icon("chevron-right.svg"))

        # Numbers only earn their space once there is more than one page
        if not self.pager_visible or total_pages <= 1:
            return

        for page in self.page_number_sequence(self.page, total_pages):
            if page is None:
                gap = QLabel("...")
                gap.setObjectName("SettingsCardDescription")
                gap.setAlignment(Qt.AlignCenter)
                gap.setFixedWidth(20)
                self.page_button_row.addWidget(gap)
                self.page_buttons.append(gap)
                continue

            btn = QPushButton(str(page + 1))
            btn.setObjectName(
                "BackupPageBtnCurrent" if page == self.page else "BackupPageBtn"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(28)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setToolTip(f"Go to page {page + 1}")
            btn.setEnabled(page != self.page)
            btn.clicked.connect(lambda checked=False, p=page: self.go_to_page(p))
            self.page_button_row.addWidget(btn)
            self.page_buttons.append(btn)

    def go_to_page(self, page: int) -> None:
        page = max(0, min(page, self.page_count() - 1))
        if page == self.page:
            return
        self.page = page
        self.render_page()

    def on_page_size_changed(self, text: str) -> None:
        try:
            size = int(text)
        except ValueError:
            return
        # Keep the first currently-visible row in view across the change
        first_visible = self.page * self.page_size
        self.page_size = size
        self.page = first_visible // size
        self.render_page()

    # ----- Formatting -----

    def format_timestamp(self, raw: str) -> str:
        """Render an ISO timestamp readably, falling back to the raw string."""
        try:
            return datetime.fromisoformat(raw).strftime("%d %b %Y, %H:%M:%S")
        except Exception:
            return raw or "Unknown date"

    def describe_contents(self, entry: dict) -> str:
        if entry.get("archive_path"):
            return "Database + snippets (zip)"
        db_path = entry.get("db_backup_path")
        export_path = entry.get("export_path")
        if db_path and export_path:
            return "Database + snippets"
        if db_path:
            return "Database only"
        if export_path:
            return "Snippets only"
        return "No files recorded"

    def contents_tooltip(self, entry: dict) -> str:
        names = [
            Path(p).name
            for p in (entry.get("archive_path"), entry.get("db_backup_path"),
                      entry.get("export_path"))
            if p
        ]
        return "\n".join(names) if names else "No files were recorded for this backup"

    def location_of(self, entry: dict) -> str:
        for key in ("archive_path", "db_backup_path", "export_path"):
            path = entry.get(key)
            if path:
                return str(Path(path).parent)
        return ""

    def show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.show()

    # ----- Actions -----

    def reveal(self, path: str) -> None:
        """Show a backup file in the OS file manager."""
        try:
            self.window.reveal_in_file_manager(path)
        except Exception:
            logger.exception("Could not reveal %s", path)

    def open_path(self, path: str) -> None:
        """Open a directory in the OS file manager."""
        try:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError(f"openUrl refused {path}")
        except Exception:
            logger.exception("Could not open %s", path)
            self.show_status(f"Could not open {path}")

    def backup_dir(self) -> Path | None:
        """Directory holding backup archives, or None if unavailable."""
        try:
            return self.window.parent.snippet_db.backup_dir()
        except Exception:
            logger.exception("Could not resolve backup directory")
            return None

    def on_open_folder(self) -> None:
        directory = self.backup_dir()
        if directory is None:
            self.show_status("Could not locate the backup folder.")
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.exception("Could not create backup folder")
            self.show_status(f"Could not open {directory}")
            return
        self.open_path(str(directory))

    def on_backup_now(self) -> None:
        """Take a backup on demand and record it in the history."""
        self.backup_now_btn.setEnabled(False)
        try:
            db = self.window.parent.snippet_db
            db_path, export_path, archive_path = db.backup_before_migration()

            if not any((db_path, export_path, archive_path)):
                self.show_status("Backup failed. See the log for details.")
                return

            self.window.record_migration_backup(db_path, export_path, archive_path)
            self.page = 0  # newest entry is on the first page
            self.refresh_state()
            self.show_status(f"Backup created in {self.backup_dir()}")
        except Exception:
            logger.exception("Manual backup failed")
            self.show_status("Backup failed. See the log for details.")
        finally:
            self.backup_now_btn.setEnabled(True)

    # ----- Styling -----

    def applyStyles(self) -> None:
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_fonts(self)

        # Icons are baked pixmaps, so they need re-tinting on a theme change
        try:
            self.back_btn.setIcon(self.themed_icon("chevron-left.svg"))
            self.next_btn.setIcon(self.themed_icon("chevron-right.svg"))
            for row in range(self.table.rowCount()):
                container = self.table.cellWidget(row, COL_ACTIONS)
                if container is None:
                    continue
                for btn in container.findChildren(QPushButton):
                    icon_name = btn.property("iconName")
                    if icon_name:
                        btn.setIcon(self.themed_icon(icon_name))
        except Exception:
            logger.debug("Backup page icon re-tint failed", exc_info=True)
