"""
A small, frameless notification toast shown when the main window is closed
to the tray. It carries the QSnippet icon and two actions:

  * Close                 - dismiss the toast.
  * Disable notifications - turn off the "notify on close" setting and persist it.

QSystemTrayIcon.showMessage() cannot carry buttons, so this purpose-built
widget replaces it. It is a frameless, always-on-top top-level window shown
without activation, so it stays visible after the main window hides, receives
button clicks, and never steals keyboard focus. It auto-dismisses after a
short delay.

Styling lives in ThemeManager (QSS rules and OBJECT_NAME_FONTS keyed on the
object names below); this widget only builds the layout.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from utils.file_utils import FileUtils

logger = logging.getLogger(__name__)

# How long the toast stays on screen before it dismisses itself.
TOAST_DURATION_MS = 10000

# Icon size inside the toast.
ICON_SIZE = 32

# Gap between the toast and the screen edge.
SCREEN_MARGIN = 16


class TrayCloseToast(QWidget):
    """Frameless 'still running in the tray' notification with action buttons."""

    disable_requested = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)
        self.setObjectName("TrayCloseToast")

        # Deliberately NOT Qt.Popup: popups close the instant they lose
        # activation, and closing the main window via the X button shifts
        # activation away from the app, so the toast would vanish before the
        # user could see it.
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # The toast never takes activation, and Qt suppresses tooltips on
        # inactive windows unless told otherwise.
        self.setAttribute(Qt.WA_AlwaysShowToolTips, True)

        self.setFixedWidth(340)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("TrayCloseToastCard")
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(10)

        # Header: icon + title + close (X)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.icon_label.setPixmap(icon.pixmap(ICON_SIZE, ICON_SIZE))
        header.addWidget(self.icon_label)

        self.title = QLabel("QSnippet")
        self.title.setObjectName("TrayCloseToastTitle")
        header.addWidget(self.title)
        header.addStretch(1)

        self.x_btn = QPushButton()
        self.x_btn.setObjectName("TrayCloseToastX")
        self.x_btn.setFixedSize(26, 26)
        self.x_btn.setIconSize(QSize(14, 14))
        self.x_btn.setCursor(Qt.PointingHandCursor)
        self.x_btn.setToolTip("Close")
        self.x_btn.clicked.connect(self.on_close)
        header.addWidget(self.x_btn, alignment=Qt.AlignTop)
        body.addLayout(header)

        # Message
        self.message = QLabel(
            "Still running in the tray. Right-click the tray icon to exit."
        )
        self.message.setObjectName("TrayCloseToastMessage")
        self.message.setWordWrap(True)
        body.addWidget(self.message)

        # Buttons: secondary on the left, primary on the right
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.disable_btn = QPushButton("Disable notifications")
        self.disable_btn.setObjectName("TrayCloseToastDisable")
        self.disable_btn.setCursor(Qt.PointingHandCursor)
        self.disable_btn.clicked.connect(self.on_disable)
        self.disable_btn.setToolTip("Stop showing this notification when the window closes")
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("TrayCloseToastClose")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.on_close)
        self.close_btn.setToolTip("Close this notification")
        buttons.addWidget(self.disable_btn, 1)
        buttons.addWidget(self.close_btn, 1)
        body.addLayout(buttons)

        # Auto-dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.close)

        self.apply_theme()

    def apply_theme(self) -> None:
        """Apply role fonts and tint the close icon for the active theme."""
        close_icon = QIcon(FileUtils.icon_path("close.svg"))
        try:
            from ui.theme_manager import ThemeManager
            ThemeManager.apply_fonts(self, default_size="small")
            tm = ThemeManager.get_instance()
            if tm:
                close_icon = tm.recolor_icon(close_icon, tm.icon_color())
        except Exception:
            logger.debug("Failed to theme tray close toast", exc_info=True)
        self.x_btn.setIcon(close_icon)

    def on_close(self) -> None:
        """Dismiss the toast (Close or X button)."""
        self.dismiss_timer.stop()
        self.close()

    def on_disable(self) -> None:
        """Emit the disable request, then dismiss the toast."""
        self.dismiss_timer.stop()
        self.disable_requested.emit()
        self.close()

    def show_near_tray(self, anchor: QRect | None = None) -> None:
        """
        Position the toast beside the tray and show it.

        Args:
            anchor (QRect | None): The tray icon's screen geometry. When valid,
                it picks the screen and whether the taskbar is at the top.
                The toast always sits in that screen's right-hand corner;
                without an anchor it uses the bottom-right of the primary
                screen.

        Returns:
            None
        """
        has_anchor = anchor is not None and anchor.isValid() and not anchor.isEmpty()
        screen = QGuiApplication.screenAt(anchor.center()) if has_anchor else None
        screen = screen or QGuiApplication.primaryScreen()
        if not screen:
            self.show()
            self.dismiss_timer.start(TOAST_DURATION_MS)
            return

        tray_at_top = has_anchor and anchor.center().y() < screen.availableGeometry().center().y()

        self.adjustSize()
        self.move(self.corner_position(screen, tray_at_top))
        self.show()
        self.raise_()
        # The final size is only certain once the wrapped message has been laid
        # out on screen, so re-pin to the corner after showing.
        self.move(self.corner_position(screen, tray_at_top))
        self.dismiss_timer.start(TOAST_DURATION_MS)

    def corner_position(self, screen, tray_at_top: bool) -> QPoint:
        """
        Return the top-left point that pins the toast to the screen's right corner.

        Uses the screen's available geometry (excluding the taskbar) and the
        toast's own frame size, so the toast sits flush against the right edge
        at the same margin on any resolution or scaling.

        Args:
            screen (QScreen): The screen to place the toast on.
            tray_at_top (bool): True to use the top-right corner (taskbar at
                the top), otherwise the bottom-right corner.

        Returns:
            QPoint: The position to move the toast to.
        """
        geo = screen.availableGeometry()
        size = self.frameGeometry().size()
        x = geo.x() + geo.width() - size.width() - SCREEN_MARGIN
        if tray_at_top:
            y = geo.y() + SCREEN_MARGIN
        else:
            y = geo.y() + geo.height() - size.height() - SCREEN_MARGIN
        return QPoint(x, y)


class DisabledSnippetToast(TrayCloseToast):
    """
    'That snippet is disabled' notification with an Enable action.

    Reuses the tray toast's layout, object names (so ThemeManager styling and
    fonts apply unchanged) and non-activating window behaviour, which keeps
    keyboard focus in the application the user was typing into. The secondary
    button dismisses; the primary button opens a menu with two choices:
    "Enable and paste" (keep the snippet enabled) or "Paste once" (paste it
    but leave it disabled). Both emit paste_requested.
    """

    # Argument: True to leave the snippet enabled afterwards, False to paste once.
    paste_requested = Signal(bool)

    def __init__(self, icon: QIcon, trigger: str, label: str = "", parent=None):
        super().__init__(icon, parent)

        name = f"\"{label}\" ({trigger})" if label else trigger
        self.message.setText(f"Snippet {name} is disabled, so it was not pasted.")

        self.disable_btn.clicked.disconnect(self.on_disable)
        self.disable_btn.setText("Dismiss")
        self.disable_btn.clicked.connect(self.on_close)
        self.disable_btn.setToolTip("Close without pasting the snippet")

        self.close_btn.clicked.disconnect(self.on_close)
        self.close_btn.setText("Paste")
        self.close_btn.setToolTip("Choose how to paste the snippet")

        menu = QMenu(self.close_btn)
        menu.setToolTipsVisible(True)
        menu.setAttribute(Qt.WA_AlwaysShowToolTips, True)
        enable_action = menu.addAction("Enable and paste", lambda: self.on_paste(True))
        enable_action.setToolTip("Turn the snippet back on, then paste it")
        once_action = menu.addAction("Paste once", lambda: self.on_paste(False))
        once_action.setToolTip("Paste it now and leave the snippet disabled")
        self.close_btn.setMenu(menu)

    def on_paste(self, keep_enabled: bool) -> None:
        """
        Emit the paste request, then dismiss the toast.

        Args:
            keep_enabled (bool): True to leave the snippet enabled afterwards.
        """
        self.dismiss_timer.stop()
        self.paste_requested.emit(keep_enabled)
        self.close()
