import re
import yaml
from pathlib import Path
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

# Subfolder that holds archived (superseded) release notices.
# Notices here are never shown as unread popups; they're only
# browsable through the read-only Release History viewer.
HISTORY_DIRNAME = "history"


class NoticeCarouselDialog(QDialog):
    # Matches the following: v0.0.7-notice, v0.0.7-dev-notice
    VERSION_PATTERN = re.compile(r"^v(?P<version>\d+(?:\.\d+)*(?:[-.][0-9A-Za-z]+)*)-notice$")

    def __init__(self,
                 notices: list[dict],
                 icon_path=QIcon,
                 parent=None,
                 window_title: str = "Updates",
                 header_text: str = "What’s new in QSnippet",
                 dismissible: bool = True) -> None:
        """
        Initialize the NoticeCarouselDialog.

        Configures dialog properties, stores notice data, initializes UI
        components, and loads the first notice for display.

        Args:
            notices (list[dict]): A list of notice dictionaries containing
                id, title, and message fields.
            icon_path (QIcon): The window icon to display.
            parent (Any): Optional parent widget.
            window_title (str): Title bar text.
            header_text (str): Heading shown above the notice title.
            dismissible (bool): Whether to show the "Do not show again"
                checkbox. Set to False for a read-only viewer (e.g. the
                Release History dialog) where dismissal doesn't apply.

        Returns:
            None
        """
        super().__init__()
        self.parent = parent
        self.notices = notices
        self.index = 0
        self.disable_future = False
        self.dismissible = dismissible

        self.setWindowTitle(window_title)
        self.setWindowIcon(icon_path)
        self.setModal(True)
        self.setMinimumSize(800, 500)

        self.initUI(header_text)
        self.load_notice()
        self.applyStyles()

    def initUI(self, header_text: str = "What’s new in QSnippet") -> None:
        """
        Initialize the dialog user interface.

        Creates labels, text display, navigation buttons, pagination
        indicator, and footer controls, and arranges them in layouts.

        Args:
            header_text (str): Heading shown above the notice title.

        Returns:
            None
        """
        self.top_label = QLabel(header_text)
        self.top_label.setObjectName("NoticeTopLabel")

        self.title_label = QLabel()
        self.title_label.setObjectName("NoticeTitleLabel")

        self.body = QTextBrowser()
        self.body.setObjectName("NoticeBody")
        self.body.setOpenExternalLinks(True)
        self.body.setAlignment(Qt.AlignCenter)
        self.body.setFrameShape(QTextBrowser.NoFrame)

        # Navigation
        self.prev_btn = QPushButton("<")
        self.prev_btn.setObjectName("PrevBtn")
        self.prev_btn.setFixedWidth(50)
        self.next_btn = QPushButton(">")
        self.next_btn.setObjectName("NextBtn")
        self.next_btn.setFixedWidth(50)
        self.prev_btn.clicked.connect(self.prev_notice)
        self.next_btn.clicked.connect(self.next_notice)

        self.pagination_label = QLabel("0 / 0")
        self.pagination_label.setObjectName("PaginationLabel")

        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addStretch()

        # Footer
        self.disable_checkbox = QCheckBox("Do not show again")
        self.disable_checkbox.setObjectName("DisableCheckbox")
        self.disable_checkbox.setVisible(self.dismissible)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("CloseBtn")
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

    def applyStyles(self) -> None:
        """Apply the app's scaled, role-correct fonts to every widget."""
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_fonts(self)

    @staticmethod
    def parse_notice_version(stem: str) -> tuple[int, ...]:
        """
        Parse a sortable version tuple from a notice filename stem.

        Extracts the numeric segments of the version (e.g. "0.0.7" from
        "v0.0.7-notice" or "v0.0.7-dev-notice") so notices can be ordered
        newest-release-first. Filenames that don't match the expected
        pattern sort as the oldest.

        Args:
            stem (str): The filename stem without extension.

        Returns:
            tuple[int, ...]: The parsed version segments, or an empty
                tuple if the stem doesn't match the expected pattern.
        """
        m = NoticeCarouselDialog.VERSION_PATTERN.match(stem)
        if not m:
            return ()

        return tuple(int(part) for part in re.findall(r"\d+", m.group("version")))

    @staticmethod
    def notice_cycle(
        notices_dir: Path,
        limit: int = NOTICE_LIMIT) -> int:
        """
        Archive excess notice files.

        Ensures only the newest-version files within the limit stay
        active (eligible to pop up as unread); anything older is moved
        into the "history" subfolder instead of being deleted, so it
        stays browsable in the Release History viewer.

        Args:
            notices_dir (Path): Directory containing notice YAML files.
            limit (int): Maximum number of notice files to keep active.

        Returns:
            int: The number of files archived.
        """
        if not notices_dir.exists():
            logger.debug(f"notices dir does not exist: {notices_dir}")
            return 0

        kept: list[tuple[tuple[int, ...], Path]] = []
        archived = 0

        for path in notices_dir.glob("*.yaml"):
            # Check if path is file
            if not path.is_file():
                continue

            # Trim stem and check regex match
            stem = path.stem
            if not NoticeCarouselDialog.VERSION_PATTERN.match(stem):
                continue

            version = NoticeCarouselDialog.parse_notice_version(stem)
            kept.append((version, path))

        # Check if we have too many active notices
        if limit is not None and limit > 0 and len(kept) > limit:
            kept.sort(key=lambda t: t[0], reverse=True)
            to_archive = kept[limit:]

            history_dir = notices_dir / HISTORY_DIRNAME
            history_dir.mkdir(exist_ok=True)

            for _, path in to_archive:
                try:
                    path.rename(history_dir / path.name)
                    archived += 1
                    logger.info(f"archived old (limit) notice: {path.name}")
                except Exception as e:
                    logger.warning(f"failed archiving {path}: {e}")

        # Return archived file count
        return archived

    @staticmethod
    def load_notices(
        notices_dir: Path,
        dismissed: set[str],
        limit: int = NOTICE_LIMIT) -> list[dict]:
        """
        Load unread notices from a directory.

        Filters valid notice files, removes excess ones beyond the
        retention limit, excludes dismissed notices, and returns
        structured notice data ordered newest-release-first.

        Args:
            notices_dir (Path): Directory containing notice YAML files.
            dismissed (set[str]): Set of dismissed notice identifiers.
            limit (int): Maximum number of notice files to retain.

        Returns:
            list[dict]: A list of unread notice dictionaries.
        """
        logger.debug(f"loading notices from {notices_dir}")

        # Run notice_cycle to cleanup excess notices
        NoticeCarouselDialog.notice_cycle(
            notices_dir,
            limit=limit
        )

        candidates: list[tuple[tuple[int, ...], str, Path]] = []

        for path in notices_dir.glob("*.yaml"):
            if not path.is_file():
                continue

            stem = path.stem
            if not NoticeCarouselDialog.VERSION_PATTERN.match(stem):
                continue

            version = NoticeCarouselDialog.parse_notice_version(stem)
            candidates.append((version, stem, path))

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

    @staticmethod
    def load_release_history(notices_dir: Path) -> list[dict]:
        """
        Load every release notice for browsing, active and archived alike.

        Unlike load_notices, this ignores dismissed state and never
        prunes or archives anything - it's meant for the read-only
        Release History viewer, not the unread-notice popup.

        Args:
            notices_dir (Path): Directory containing notice YAML files
                (its "history" subfolder is included automatically).

        Returns:
            list[dict]: All notices, sorted newest-release-first.
        """
        search_dirs = [notices_dir, notices_dir / HISTORY_DIRNAME]

        candidates: list[tuple[tuple[int, ...], str, Path]] = []
        for d in search_dirs:
            if not d.exists():
                continue

            for path in d.glob("*.yaml"):
                if not path.is_file():
                    continue

                stem = path.stem
                if not NoticeCarouselDialog.VERSION_PATTERN.match(stem):
                    continue

                version = NoticeCarouselDialog.parse_notice_version(stem)
                candidates.append((version, stem, path))

        if not candidates:
            logger.debug("no notice files found for release history")
            return []

        candidates.sort(key=lambda t: t[0], reverse=True)

        history: list[dict] = []
        for _, nid, path in candidates:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                history.append({
                    "id": nid,
                    "title": data.get("title", "Update Notice"),
                    "message": data.get("message", "")
                })
            except Exception as e:
                logger.error(f"failed to load {path}: {e}")

        return history