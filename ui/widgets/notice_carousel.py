import re
import yaml
from pathlib import Path
from datetime import datetime, timedelta
import logging

from PySide6.QtWidgets import (
    QDialog, QLabel, QTextBrowser, QPushButton,
    QHBoxLayout, QVBoxLayout, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)

# Set max limit on notices
# This will avoid loading in too many notices
NOTICE_LIMIT = 10

# Set limit to how old notices can be
# Any notice older than this will not
# be shown, and automatically deleted.
MAX_DAY_COUNT = 30


class NoticeCarouselDialog(QDialog):
    # Matches the following: mm-dd-yyyy-notice
    DATE_PATTERN = re.compile(r"^(?P<mm>\d{2})-(?P<dd>\d{2})-(?P<yyyy>\d{4})-notice$")

    def __init__(self, 
                 notices: list[dict],
                 icon_path=QIcon,
                 parent=None) -> None:
        """
        Initialize the NoticeCarouselDialog.

        Configures dialog properties, stores notice data, initializes UI
        components, and loads the first notice for display.

        Args:
            notices (list[dict]): A list of notice dictionaries containing
                id, title, and message fields.
            icon_path (QIcon): The window icon to display.
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__()
        self.parent = parent
        self.notices = notices
        self.index = 0
        self.disable_future = False

        self.setWindowTitle("Updates")
        self.setWindowIcon(icon_path)
        self.setModal(True)
        self.setMinimumSize(520, 340)

        self.initUI()
        self.load_notice()

    def initUI(self) -> None:
        """
        Initialize the dialog user interface.

        Creates labels, text display, navigation buttons, pagination
        indicator, and footer controls, and arranges them in layouts.

        Returns:
            None
        """
        self.top_label = QLabel("What’s new in QSnippet")
        self.top_label.setStyleSheet("font-weight: bold; font-size: 18px;")

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.body.setAlignment(Qt.AlignCenter)
        self.body.setFrameShape(QTextBrowser.NoFrame)

        # Navigation
        self.prev_btn = QPushButton("<")
        self.prev_btn.setFixedWidth(50)
        self.next_btn = QPushButton(">")
        self.next_btn.setFixedWidth(50)
        self.prev_btn.clicked.connect(self.prev_notice)
        self.next_btn.clicked.connect(self.next_notice)

        self.pagination_label = QLabel("0 / 0")

        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addStretch()

        # Footer
        self.disable_checkbox = QCheckBox("Do not show again")

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)

        footer_layout = QHBoxLayout()
        footer_layout.addWidget(self.disable_checkbox)
        footer_layout.addStretch()
        footer_layout.addWidget(self.close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.top_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.body, 1)
        layout.addLayout(nav_layout)
        layout.addWidget(self.pagination_label, alignment=Qt.AlignCenter)
        layout.addLayout(footer_layout)

    # HELPER FUNCTIONS

    def load_notice(self) -> None:
        """
        Load and display the current notice.

        Updates the title, message content, navigation button states,
        and pagination label based on the current index.

        Returns:
            None
        """
        notice = self.notices[self.index]
        notice_count = len(self.notices)
        self.title_label.setText(notice.get("title", "Update"))
        self.body.setMarkdown(notice.get("message", ""))

        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < notice_count - 1)
        self.pagination_label.setText(f"{self.index + 1} / {notice_count}")

    def prev_notice(self) -> None:
        """
        Navigate to the previous notice if available.

        Returns:
            None
        """
        if self.index > 0:
            self.index -= 1
            self.load_notice()

    def next_notice(self) -> None:
        """
        Navigate to the next notice if available.

        Returns:
            None
        """
        if self.index < len(self.notices) - 1:
            self.index += 1
            self.load_notice()

    def accept(self) -> None:
        """
        Handle dialog acceptance.

        Stores the state of the disable checkbox and closes the dialog.

        Returns:
            None
        """
        self.disable_future = self.disable_checkbox.isChecked()
        super().accept()

    def reject(self) -> None:
        """
        Handle dialog rejection.

        Stores the state of the disable checkbox and closes the dialog.

        Returns:
            None
        """
        self.disable_future = self.disable_checkbox.isChecked()
        super().reject()

    @staticmethod
    def parse_notice_dt(stem: str, path: Path) -> datetime:
        """
        Parse a datetime from a notice filename stem.

        If the filename matches the expected pattern, extracts the date.
        Otherwise, falls back to the file modification time.

        Args:
            stem (str): The filename stem without extension.
            path (Path): The full path to the notice file.

        Returns:
            datetime: The parsed or fallback datetime.
        """
        m = NoticeCarouselDialog.DATE_PATTERN.match(stem)
        if not m:
            return datetime.fromtimestamp(path.stat().st_mtime)

        try:
            return datetime(
                int(m.group("yyyy")),
                int(m.group("mm")),
                int(m.group("dd")),
            )
        except ValueError:
            return datetime.fromtimestamp(path.stat().st_mtime)

    @staticmethod
    def notice_cycle(
        notices_dir: Path,
        limit: int = NOTICE_LIMIT,
        max_day_count: int = MAX_DAY_COUNT) -> int:
        """
        Clean up outdated or excess notice files.

        Deletes notices older than the specified maximum age and
        ensures only the newest files within the limit are retained.

        Args:
            notices_dir (Path): Directory containing notice YAML files.
            limit (int): Maximum number of notice files to retain.
            max_day_count (int): Maximum age in days before deletion.

        Returns:
            int: The number of files deleted.
        """
        if not notices_dir.exists():
            logger.debug(f"notices dir does not exist: {notices_dir}")
            return 0

        now = datetime.now()
        cutoff = now - timedelta(days=max_day_count) if (max_day_count and max_day_count > 0) else None

        kept: list[tuple[datetime, Path]] = []
        deleted = 0

        for path in notices_dir.glob("*.yaml"):
            # Check if path is file
            if not path.is_file():
                continue

            # Trim stemp and check regex match
            stem = path.stem
            if not NoticeCarouselDialog.DATE_PATTERN.match(stem):
                continue

            dt = NoticeCarouselDialog.parse_notice_dt(stem, path)

            # Delete notices older than max_day_count
            if cutoff is not None and dt < cutoff:
                try:
                    path.unlink(missing_ok=True)
                    deleted += 1
                    logger.info(f"deleted old (age) notice: {path.name}")
                except Exception as e:
                    logger.warning(f"failed deleting {path}: {e}")
                continue

            kept.append((dt, path))

        # Check if we have too many notices
        if limit is not None and limit > 0 and len(kept) > limit:
            kept.sort(key=lambda t: t[0], reverse=True)
            to_delete = kept[limit:]

            for _, path in to_delete:
                try:
                    path.unlink(missing_ok=True)
                    deleted += 1
                    logger.info(f"deleted old (limit) notice: {path.name}")
                except Exception as e:
                    logger.warning(f"failed deleting {path}: {e}")

        # Return deleted file count
        return deleted

    @staticmethod
    def load_notices(
        notices_dir: Path,
        dismissed: set[str],
        limit: int = NOTICE_LIMIT,
        max_day_count: int = MAX_DAY_COUNT) -> list[dict]:
        """
        Load unread notices from a directory.

        Filters valid notice files, removes outdated ones, excludes
        dismissed notices, and returns structured notice data.

        Args:
            notices_dir (Path): Directory containing notice YAML files.
            dismissed (set[str]): Set of dismissed notice identifiers.
            limit (int): Maximum number of notice files to retain.
            max_day_count (int): Maximum age in days before deletion.

        Returns:
            list[dict]: A list of unread notice dictionaries.
        """
        logger.debug(f"loading notices from {notices_dir}")

        # Run notice_cycle to cleanup old notices
        NoticeCarouselDialog.notice_cycle(
            notices_dir,
            limit=limit,
            max_day_count=max_day_count
        )

        candidates: list[tuple[datetime, str, Path]] = []

        for path in notices_dir.glob("*.yaml"):
            if not path.is_file():
                continue

            stem = path.stem
            if not NoticeCarouselDialog.DATE_PATTERN.match(stem):
                continue

            dt = NoticeCarouselDialog.parse_notice_dt(stem, path)
            candidates.append((dt, stem, path))

        if not candidates:
            logger.debug("no notice files found")
            return []

        candidates.sort(key=lambda t: t[0], reverse=True)

        unread: list[dict] = []
        for _, nid, path in candidates:
            if nid in dismissed:
                continue

            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                unread.append({
                    "id": nid,
                    "title": data.get("title", "Update Notice"),
                    "message": data.get("message", "")
                })
                logger.debug(f"loaded notice {nid}")
            except Exception as e:
                logger.error(f"failed to load {path}: {e}")

        return unread