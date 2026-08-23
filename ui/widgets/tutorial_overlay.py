import html
import logging
from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QObject, QRect, QPoint, QSize, QEvent, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QIcon

logger = logging.getLogger(__name__)

# Padding drawn around a highlighted widget so its border isn't clipped
SPOTLIGHT_PADDING = 6

# Gap between the spotlight edge and the coach-mark bubble
BUBBLE_GAP = 14

# Bubble width. Deliberately a fixed pixel value, and the same for every
# step: QFontMetrics' averageCharWidth over-reports badly (12px for a 9pt
# face), so deriving it from the font made the bubble far too wide, while
# letting QLabel's word-wrap hint decide made it vary step to step and clip
# the text. This is the widest the bubble ever used to get.
BUBBLE_WIDTH = 460

# Spare pixels on the footer row. The layout distributes widths as integers
# and can land a pixel short of a button's hint, which clips the last glyph.
FOOTER_SLACK = 4

# Typing demo pacing, in milliseconds
DEMO_START_MS = 750     # beat before the first character, so it's not missed
DEMO_TYPE_MS = 100       # per character
DEMO_HOLD_MS = 750      # trigger sits complete before it expands
DEMO_CARET = "▌"   # block caret shown at the typing position


@dataclass
class TypingDemo:
    """
    A trigger typed out a character at a time, then replaced by what it
    expands to; the app's whole premise, shown rather than described.

    Args:
        trigger (str): The trigger to type, e.g. "/getting-started".
        expansion (str): Rich text the trigger is replaced with once typed.
    """
    trigger: str
    expansion: str


@dataclass
class TutorialStep:
    """
    A single stop in the guided tour.

    Args:
        title (str): Bubble heading.
        body (str): Bubble text. Rich text is allowed.
        target (Callable | None): Returns the widget to spotlight, a list
            of widgets to cover with one spotlight, or None for a centered
            step with no highlight. Resolved lazily at display time so
            widgets that don't exist yet (or are hidden) never break the
            tour.
        before (Callable | None): Runs before the step is shown; used to
            put the app in the state the step describes (e.g. open the
            new-snippet form).
        after (Callable | None): Runs when the step is left in the forward
            direction; used to undo whatever before() set up.
        demo (TypingDemo | None): An optional typing demo played beneath
            the body text whenever the step is shown.
        host (Callable | None): Returns the window the spotlight is drawn
            over. Defaults to the main window; a step that opens a dialog
            returns that dialog so the tour can point inside it.
        branch (Callable | None): Returns a TutorialBranch to detour into
            when the reader asks to see more. Keeping it a callable means
            a branch that points inside a dialog isn't built until the
            reader actually asks for it.
        branch_label (str): Text on the button that enters the branch.
        action (Callable | None): A one-off the reader can run from this
            step instead of branching, such as starting vault setup. The
            tour ends before it runs.
        action_label (str): Text on the button that runs the action.
    """
    title: str
    body: str
    target: Callable | None = None
    before: Callable | None = None
    after: Callable | None = None
    demo: "TypingDemo | None" = None
    host: Callable | None = None
    branch: Callable | None = None
    branch_label: str = "Learn more"
    action: Callable | None = None
    action_label: str = ""


@dataclass
class TutorialBranch:
    """
    An optional detour off the main tour.

    Args:
        title (str): Short name shown in the progress line, e.g. "Settings".
        steps (list[TutorialStep]): The detour's steps, in order.
        cleanup (Callable | None): Always runs when the detour is left,
            whether it was finished or cut short, so a branch that opened
            a dialog can be relied on to close it again.
    """
    title: str
    steps: list["TutorialStep"]
    cleanup: Callable | None = None


class TutorialBubble(QFrame):
    """
    The coach-mark panel: heading, body copy, progress text and controls.

    Lives as a child of TutorialOverlay and is repositioned next to the
    current spotlight each time a step is shown.
    """

    backRequested = Signal()
    nextRequested = Signal()
    skipRequested = Signal()
    closeRequested = Signal()
    extraRequested = Signal()
    layoutChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TutorialBubble")
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Typing demo state
        self.step_body = ""
        self.demo = None
        self.demo_typed = 0
        self.demo_expanded = False
        self.demo_held_ms = 0
        self.caret_visible = True
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self.on_demo_tick)

        self.initUI()
        self.applyStyles()

    def initUI(self) -> None:
        """
        Build the bubble layout.

        Returns:
            None
        """
        self.title_label = QLabel()
        self.title_label.setObjectName("TutorialTitle")
        self.title_label.setWordWrap(True)

        # Sits in the top-right corner, and only on a step that has a demo
        self.replay_btn = QPushButton()
        self.replay_btn.setObjectName("TutorialReplayBtn")
        self.replay_btn.setToolTip("Play the animation again")
        self.replay_btn.setCursor(Qt.PointingHandCursor)
        self.replay_btn.setFlat(True)
        self.replay_btn.setFixedSize(26, 26)
        self.replay_btn.setIconSize(QSize(16, 16))
        self.replay_btn.clicked.connect(self.replay_demo)
        self.replay_btn.hide()

        # Always available, to the right of replay: ends the tour outright,
        # unlike Skip, which only leaves the current branch
        self.close_btn = QPushButton()
        self.close_btn.setObjectName("TutorialCloseBtn")
        self.close_btn.setToolTip("Close the tour")
        #self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.clicked.connect(self.closeRequested.emit)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label, 1)
        title_row.addWidget(self.replay_btn, 0, Qt.AlignTop)
        title_row.addWidget(self.close_btn, 0, Qt.AlignTop)

        self.body_label = QLabel()
        self.body_label.setObjectName("TutorialBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.RichText)
        self.body_label.setOpenExternalLinks(True)
        self.body_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        # Top-left, so the trigger being typed starts where the finished text
        # starts instead of floating in the middle of the space held for it
        self.body_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.progress_label = QLabel()
        self.progress_label.setObjectName("TutorialProgress")

        # Skip, Back and the optional extra share the standard button role;
        # only Next is primary
        self.extra_btn = QPushButton()
        self.extra_btn.setObjectName("TutorialBtn")
        self.extra_btn.setCursor(Qt.PointingHandCursor)
        self.extra_btn.clicked.connect(self.extraRequested.emit)
        self.extra_btn.hide()

        self.skip_btn = QPushButton("Skip tour")
        self.skip_btn.setObjectName("TutorialBtn")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.clicked.connect(self.skipRequested.emit)

        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("TutorialBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.backRequested.emit)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("TutorialNextBtn")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setDefault(True)
        self.next_btn.clicked.connect(self.nextRequested.emit)

        # Buttons keep their natural size; without this the layout squeezes
        # them once the body text arrives and clips their labels
        for button in (self.extra_btn, self.skip_btn, self.back_btn, self.next_btn):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(0, 0, 0, 0)
        self.footer.setSpacing(8)
        self.footer.addWidget(self.progress_label)
        self.footer.addStretch()
        self.footer.addWidget(self.extra_btn)
        self.footer.addWidget(self.skip_btn)
        self.footer.addWidget(self.back_btn)
        self.footer.addWidget(self.next_btn)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 16, 18, 14)
        self.main_layout.setSpacing(10)
        self.main_layout.addLayout(title_row)
        self.main_layout.addWidget(self.body_label)
        self.main_layout.addLayout(self.footer)

    def load_step(self, step: TutorialStep, index: int, total: int,
                  branch_title: str = "") -> None:
        """
        Show a step's content and update the navigation controls.

        Args:
            step (TutorialStep): The step being displayed.
            index (int): Zero-based position within the current sequence.
            total (int): Number of steps in the current sequence.
            branch_title (str): Name of the detour being shown, or "" when
                this is the main tour.

        Returns:
            None
        """
        self.stop_demo()
        self.title_label.setText(step.title)
        self.step_body = step.body
        self.back_btn.setEnabled(index > 0 or bool(branch_title))

        last = index == total - 1
        in_branch = bool(branch_title)

        if in_branch:
            self.progress_label.setText(f"{branch_title} · {index + 1} of {total}")
            self.next_btn.setText("Back to tour" if last else "Next")
            # On the last step Next already returns, so don't offer it twice
            self.skip_btn.setText("Back to tour")
            self.skip_btn.setVisible(not last)
        else:
            self.progress_label.setText(f"{index + 1} of {total}")
            self.next_btn.setText("Finish" if last else "Next")
            self.skip_btn.setText("Skip tour")
            self.skip_btn.setVisible(not last)

        if step.branch is not None:
            self.extra_btn.setText(step.branch_label)
            self.extra_btn.show()
        elif step.action is not None and step.action_label:
            self.extra_btn.setText(step.action_label)
            self.extra_btn.show()
        else:
            self.extra_btn.hide()

        self.demo = step.demo
        self.demo_typed = 0
        self.demo_held_ms = 0
        self.caret_visible = True
        self.replay_btn.setVisible(self.demo is not None)

        # Lay out showing the finished text, so the size measured below (and
        # held for the whole demo) is the size the step ends at
        self.demo_expanded = True
        self.render_body()
        self.applyStyles()
        self.fit_to_content()

        if self.demo is not None:
            self.start_demo()

    def fit_to_content(self) -> None:
        """
        Size the bubble to exactly what this step needs.

        Width is the standard width, widened if the footer needs more room:
        button labels and their padding grow with the UI scale, and pinning
        the bubble narrower than the row requires squeezed the buttons until
        "Skip tour" was clipped. Height then follows from heightForWidth,
        which adjustSize() gets wrong for word-wrapped labels and was
        cutting the last line off the longer steps.

        Returns:
            None
        """
        self.main_layout.activate()

        # The footer's sizeHint is the row's true width; its minimumSize
        # under-reports badly (321 against a 785 hint), which is what let the
        # buttons be squeezed until their labels clipped.
        margins = self.main_layout.contentsMargins()
        footer_width = (
            self.footer.sizeHint().width()
            + margins.left() + margins.right()
            + FOOTER_SLACK
        )

        width = max(BUBBLE_WIDTH, footer_width)
        if self.width() != width or self.minimumWidth() != width:
            self.setFixedWidth(width)
            self.main_layout.activate()

        height = self.heightForWidth(width)
        if height <= 0:
            height = self.sizeHint().height()

        height = max(height, self.minimumSizeHint().height())
        self.resize(width, height)
        self.main_layout.activate()

    # ----- TYPING DEMO -----

    def render_body(self) -> None:
        """
        Rebuild the body text for the current step and demo state.

        Returns:
            None
        """
        parts = []
        if self.step_body:
            parts.append(self.step_body)

        if self.demo is not None:
            parts.append(self.demo.expansion if self.demo_expanded else self.demo_html())

        self.body_label.setText("<br><br>".join(parts))

    def demo_html(self) -> str:
        """
        Render the part of the trigger typed so far, with a caret.

        The trigger is drawn in the ordinary text colour, bold, so it reads
        as something being typed rather than as a highlight.

        Returns:
            str: Rich text for the in-progress trigger.
        """
        typed = html.escape(self.demo.trigger[:self.demo_typed])
        caret = DEMO_CARET if self.caret_visible else "&nbsp;"

        return f"<b>{typed}</b>{caret}"

    def start_demo(self) -> None:
        """
        Begin typing the trigger out.

        The body is measured while the finished text is showing and then
        held at that height, so the bubble is exactly the same size while
        typing as it is once the text arrives; it never grows or shifts
        under the reader mid-animation.

        Returns:
            None
        """
        # fit_to_content has already laid the bubble out around the finished
        # text, so the label's height here is the one to hold on to
        self.body_label.setMinimumHeight(self.body_label.height())

        self.demo_expanded = False
        self.demo_typed = 0
        self.demo_held_ms = 0
        self.caret_visible = True
        self.render_body()

        self.demo_timer.start(DEMO_START_MS)

    def replay_demo(self) -> None:
        """
        Play the current step's demo again from the top.

        Returns:
            None
        """
        if self.demo is None:
            return

        # The held height is already the finished size, so replaying keeps
        # the bubble exactly where and how big it is
        self.start_demo()

    def on_demo_tick(self) -> None:
        """
        Advance the demo: type the next character, hold, then expand.

        Returns:
            None
        """
        if self.demo is None or self.demo_expanded:
            self.demo_timer.stop()
            return

        self.demo_timer.setInterval(DEMO_TYPE_MS)

        if self.demo_typed < len(self.demo.trigger):
            self.demo_typed += 1
            self.render_body()
            return

        # Trigger is complete: blink the caret briefly, then expand
        self.demo_held_ms += DEMO_TYPE_MS
        if self.demo_held_ms < DEMO_HOLD_MS:
            self.caret_visible = not self.caret_visible
            self.render_body()
            return

        self.expand_demo()

    def expand_demo(self) -> None:
        """
        Swap the typed trigger for what it expands to and stop the demo.

        The swap is instant because that is what a real expansion looks
        like; QSnippet replaces the trigger in one go rather than typing
        the replacement out.

        Returns:
            None
        """
        self.demo_timer.stop()
        self.demo_expanded = True
        self.caret_visible = False
        self.render_body()

    def stop_demo(self) -> None:
        """
        Halt any running demo and release the height held for it.

        Returns:
            None
        """
        self.demo_timer.stop()
        self.demo = None
        self.demo_expanded = False
        self.body_label.setMinimumHeight(0)

    def applyStyles(self) -> None:
        """
        Apply the app's scaled, role-correct fonts to every widget.

        Buttons are left to the global QSS, which sizes them from the
        user's button padding setting like every other button in the app.

        Returns:
            None
        """
        from utils.file_utils import FileUtils
        from ui.theme_manager import ThemeManager

        ThemeManager.apply_fonts(self)

        # Width and height are settled together in fit_to_content: QLabel's
        # word-wrap size hint picks a different width for each body of text,
        # which made the bubble narrower on some steps than others and
        # clipped the copy.

        # Re-tint the title-row icons for the active theme, the way the
        # toolbar and menus tint theirs
        tm = ThemeManager.get_instance()
        for button, name in ((self.replay_btn, "refresh.svg"),
                             (self.close_btn, "close.svg")):
            icon = QIcon(FileUtils.icon_path(name))
            button.setIcon(tm.recolor_icon(icon, tm.icon_color()) if tm else icon)


class TutorialOverlay(QWidget):
    """
    Full-window dimming layer with a cut-out spotlight and a coach-mark bubble.

    The overlay is a child of the main window rather than a separate
    top-level widget so it always tracks the window's geometry, stacking
    and theme. It swallows mouse input over the dimmed area, which keeps
    the app in the state each step describes while the tour runs.
    """

    backRequested = Signal()
    nextRequested = Signal()
    skipRequested = Signal()
    closeRequested = Signal()
    extraRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TutorialOverlay")
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.spotlight = QRect()

        self.bubble = TutorialBubble(self)
        self.bubble.backRequested.connect(self.backRequested.emit)
        self.bubble.nextRequested.connect(self.nextRequested.emit)
        self.bubble.skipRequested.connect(self.skipRequested.emit)
        self.bubble.closeRequested.connect(self.closeRequested.emit)
        self.bubble.extraRequested.connect(self.extraRequested.emit)
        self.bubble.layoutChanged.connect(self.position_bubble)

        shadow = QGraphicsDropShadowEffect(self.bubble)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 140))
        self.bubble.setGraphicsEffect(shadow)

        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

    # ----- STEP DISPLAY -----

    def show_step(self, step: TutorialStep, index: int, total: int,
                  branch_title: str = "") -> None:
        """
        Display a step: move the spotlight, refill the bubble, reposition it.

        Args:
            step (TutorialStep): The step being displayed.
            index (int): Zero-based position within the current sequence.
            total (int): Number of steps in the current sequence.
            branch_title (str): Name of the detour being shown, or "" when
                this is the main tour.

        Returns:
            None
        """
        self.bubble.load_step(step, index, total, branch_title)
        self.spotlight = self.resolve_spotlight(step)
        self.position_bubble()
        self.update()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    def resolve_spotlight(self, step: TutorialStep) -> QRect:
        """
        Map a step's target into overlay coordinates.

        A step may name one widget or several. Several are covered by a
        single spotlight spanning them all, which is how a row of related
        controls is highlighted without a wrapper widget to point at.

        Args:
            step (TutorialStep): The step whose target should be resolved.

        Returns:
            QRect: The padded rect to cut out, or an empty rect when the
                step has no target or none of its targets are available.
        """
        if step.target is None:
            return QRect()

        try:
            target = step.target()
        except Exception:
            logger.exception("Tutorial step target could not be resolved")
            return QRect()

        if target is None:
            return QRect()

        widgets = list(target) if isinstance(target, (list, tuple, set)) else [target]

        rect = QRect()
        for widget in widgets:
            part = self.widget_rect(widget)
            if part is None:
                continue
            rect = part if rect.isNull() else rect.united(part)

        if rect.isNull():
            return QRect()

        return rect.intersected(self.rect())

    def widget_rect(self, widget) -> QRect | None:
        """
        Return a padded rect for one widget in overlay coordinates.

        Args:
            widget (QWidget): The widget to measure.

        Returns:
            QRect | None: The padded rect, or None when the widget is
                missing, hidden or has no size worth highlighting.
        """
        if widget is None:
            return None

        # A hidden or zero-sized widget maps to a meaningless rect; skip it
        # rather than spotlighting empty space.
        try:
            if not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
                return None
            top_left = widget.mapTo(self.parentWidget(), QPoint(0, 0))
        except (RuntimeError, AttributeError):
            logger.debug("Tutorial target widget is no longer usable")
            return None

        return QRect(top_left, widget.size()).adjusted(
            -SPOTLIGHT_PADDING, -SPOTLIGHT_PADDING,
            SPOTLIGHT_PADDING, SPOTLIGHT_PADDING,
        )

    def position_bubble(self) -> None:
        """
        Place the bubble beside the spotlight, or centered when there is none.

        Prefers below the spotlight, then above, then to the right or left.
        When the target is large enough that every position overlaps it -
        a step highlighting the whole form on a short window, say - the
        bubble goes wherever it hides the least of the target rather than
        landing dead centre on top of it.

        Returns:
            None
        """
        self.bubble.fit_to_content()
        size = self.bubble.size()
        area = self.rect()

        if self.spotlight.isNull() or self.spotlight.isEmpty():
            self.center_bubble()
            return

        spot = self.spotlight
        candidates = [
            # below
            QPoint(spot.center().x() - size.width() // 2, spot.bottom() + BUBBLE_GAP),
            # above
            QPoint(spot.center().x() - size.width() // 2, spot.top() - BUBBLE_GAP - size.height()),
            # right
            QPoint(spot.right() + BUBBLE_GAP, spot.center().y() - size.height() // 2),
            # left
            QPoint(spot.left() - BUBBLE_GAP - size.width(), spot.center().y() - size.height() // 2),
        ]

        best = None
        best_overlap = None

        for point in candidates:
            clamped = self.clamp_to_area(QRect(point, size), area)
            overlap = clamped.intersected(spot)
            covered = overlap.width() * overlap.height()

            if covered == 0:
                self.bubble.move(clamped.topLeft())
                return

            if best_overlap is None or covered < best_overlap:
                best, best_overlap = clamped, covered

        if best is None:
            self.center_bubble()
            return

        self.bubble.move(best.topLeft())

    def center_bubble(self) -> None:
        """
        Park the bubble in the middle of the overlay.

        Returns:
            None
        """
        size = self.bubble.size()
        area = self.rect()
        self.bubble.move(
            area.center().x() - size.width() // 2,
            area.center().y() - size.height() // 2,
        )

    def clamp_to_area(self, rect: QRect, area: QRect) -> QRect:
        """
        Keep a rect fully inside the overlay.

        Args:
            rect (QRect): The rect to constrain.
            area (QRect): The bounding area.

        Returns:
            QRect: The constrained rect.
        """
        left = area.left() + BUBBLE_GAP
        top = area.top() + BUBBLE_GAP

        # A bubble larger than the area would otherwise clamp to a negative
        # position and disappear off the top-left; pin it to the near edge so
        # the title and the start of the text stay readable.
        right = max(left, area.right() - rect.width() - BUBBLE_GAP)
        bottom = max(top, area.bottom() - rect.height() - BUBBLE_GAP)

        x = min(max(rect.left(), left), right)
        y = min(max(rect.top(), top), bottom)
        return QRect(QPoint(x, y), rect.size())

    # ----- PAINTING -----

    def paintEvent(self, event) -> None:
        """
        Dim the window and cut a rounded hole around the current target.

        The hole is produced with an odd-even fill rather than a clear
        composition mode so the dimming stays translucent over whatever
        the window is already painting.

        Returns:
            None
        """
        from ui.theme_manager import ThemeManager

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        tm = ThemeManager.get_instance()
        is_dark = tm.is_dark if tm else True
        scrim = QColor(0, 0, 0, 165) if is_dark else QColor(15, 15, 15, 120)
        accent = ThemeManager.qcolor("accent", "#60cdff")

        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addRect(self.rect())

        has_spot = not (self.spotlight.isNull() or self.spotlight.isEmpty())
        if has_spot:
            path.addRoundedRect(self.spotlight, 8, 8)

        painter.fillPath(path, scrim)

        if has_spot:
            pen = QPen(accent)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.spotlight, 8, 8)

        painter.end()

    # ----- INPUT -----

    def mousePressEvent(self, event) -> None:
        """Swallow clicks so the app can't be driven out from under a step."""
        event.accept()

    def keyPressEvent(self, event) -> None:
        """
        Drive the tour from the keyboard.

        Enter, Space and Right advance; Left and Backspace go back;
        Escape skips.

        Returns:
            None
        """
        key = event.key()
        if key == Qt.Key_Escape:
            self.skipRequested.emit()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_Right):
            self.nextRequested.emit()
        elif key in (Qt.Key_Left, Qt.Key_Backspace):
            self.backRequested.emit()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        """
        Track the host window so the overlay always covers it.

        Returns:
            bool: False, so the window still handles the event itself.
        """
        if obj is self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self.setGeometry(self.parentWidget().rect())
            self.position_bubble()
            self.update()
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.position_bubble()

    def teardown(self) -> None:
        """
        Detach from the host window and delete the overlay.

        Returns:
            None
        """
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.hide()
        self.deleteLater()


class TutorialController(QObject):
    """
    Runs a list of TutorialSteps against the main window.

    The controller owns the overlay lifecycle, per-step setup and teardown
    actions, and reports how the tour ended so the caller can persist it.
    """

    # True when the tour ran to the end, False when the user skipped it
    finished = Signal(bool)

    def __init__(self, window, steps: list[TutorialStep], parent=None):
        """
        Initialize the controller.

        Args:
            window (QWidget): The main window the overlay is drawn over.
            steps (list[TutorialStep]): Ordered steps to present.
            parent (QObject): Optional parent QObject.

        Returns:
            None
        """
        super().__init__(parent)
        self.window = window
        self.steps = steps
        self.index = 0
        self.overlay = None
        self.active = False

        # Detour state; branch is None whenever the main tour is showing
        self.branch = None
        self.branch_index = 0
        self.branch_origin = 0

    # ----- CURRENT POSITION -----

    def sequence(self) -> list:
        """Return the steps currently being shown: the branch, or the tour."""
        return self.branch.steps if self.branch is not None else self.steps

    def position(self) -> int:
        """Return the index within the current sequence."""
        return self.branch_index if self.branch is not None else self.index

    def current_step(self) -> TutorialStep:
        """Return the step on screen."""
        return self.sequence()[self.position()]

    def start(self) -> None:
        """
        Build the overlay and show the first step.

        Returns:
            None
        """
        if self.active or not self.steps:
            logger.debug("Tutorial start ignored (active=%s, steps=%d)", self.active, len(self.steps))
            return

        logger.info("Starting tutorial with %d steps", len(self.steps))
        self.index = 0
        self.branch = None
        self.active = True

        self.overlay = self.build_overlay(self.window)

        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        if tm:
            tm.themeChanged.connect(self.refresh_step)

        self.overlay.show()
        self.apply_step()

    def build_overlay(self, host) -> TutorialOverlay:
        """
        Create an overlay over *host* and wire its controls up.

        Args:
            host (QWidget): The window the overlay should cover.

        Returns:
            TutorialOverlay: The new overlay.
        """
        overlay = TutorialOverlay(host)
        overlay.backRequested.connect(self.go_back)
        overlay.nextRequested.connect(self.go_next)
        overlay.skipRequested.connect(self.skip)
        overlay.closeRequested.connect(self.quit_tour)
        overlay.extraRequested.connect(self.run_extra)
        return overlay

    def host_for(self, step: TutorialStep):
        """
        Return the window a step's spotlight belongs on.

        Args:
            step (TutorialStep): The step about to be shown.

        Returns:
            QWidget: The step's own host, or the main window.
        """
        if step.host is None:
            return self.window

        try:
            host = step.host()
        except Exception:
            logger.exception("Tutorial step host could not be resolved")
            return self.window

        return host if host is not None else self.window

    def move_overlay_to(self, host) -> None:
        """
        Make sure the overlay is covering *host*, rebuilding it if not.

        A step that opens a dialog needs the spotlight drawn on the dialog
        rather than on the main window behind it.

        Args:
            host (QWidget): The window the overlay should cover.

        Returns:
            None
        """
        current = None
        if self.overlay is not None:
            try:
                current = self.overlay.parentWidget()
            except RuntimeError:
                # The host was destroyed and took the overlay with it
                self.overlay = None

        if self.overlay is not None and current is host:
            return

        previous, self.overlay = self.overlay, self.build_overlay(host)
        self.overlay.show()

        if previous is not None:
            try:
                previous.teardown()
            except RuntimeError:
                pass

    def apply_step(self) -> None:
        """
        Run the current step's setup action and display it.

        The display is deferred by one event-loop turn so any layout the
        setup action triggers (switching the right-hand stack, for
        example) has settled before the spotlight rect is measured.

        Returns:
            None
        """
        step = self.current_step()

        if step.before is not None:
            try:
                step.before()
            except Exception:
                logger.exception("Tutorial step setup failed: %s", step.title)

        QTimer.singleShot(0, self.refresh_step)

    def refresh_step(self) -> None:
        """
        Re-measure and redraw the current step.

        Host resolution happens here rather than in apply_step so a step
        that opened a dialog has had an event-loop turn to lay it out
        before the spotlight is measured against it.

        Also used as the themeChanged handler so the bubble and spotlight
        follow a theme switch made mid-tour.

        Returns:
            None
        """
        if not self.active:
            return

        step = self.current_step()
        self.move_overlay_to(self.host_for(step))

        if self.overlay is None:
            return

        title = self.branch.title if self.branch is not None else ""
        self.overlay.show_step(step, self.position(), len(self.sequence()), title)

    def run_after(self, step: TutorialStep) -> None:
        """
        Run a step's teardown action.

        Args:
            step (TutorialStep): The step being left.

        Returns:
            None
        """
        if step.after is not None:
            try:
                step.after()
            except Exception:
                logger.exception("Tutorial step teardown failed: %s", step.title)

    # ----- BRANCHES -----

    def run_extra(self) -> None:
        """
        Handle the step's secondary button: enter a branch, or run an action.

        An action ends the tour first, so the overlay is gone before
        whatever it opens appears.

        Returns:
            None
        """
        if not self.active:
            return

        step = self.current_step()

        if step.branch is not None:
            self.enter_branch(step)
            return

        if step.action is not None:
            action = step.action
            logger.info("Tutorial action taken on step '%s'", step.title)
            self.stop(completed=True)
            try:
                action()
            except Exception:
                logger.exception("Tutorial step action failed: %s", step.title)

    def enter_branch(self, step: TutorialStep) -> None:
        """
        Detour into a step's branch.

        Args:
            step (TutorialStep): The main-tour step being detoured from.

        Returns:
            None
        """
        if self.branch is not None:
            return

        try:
            branch = step.branch()
        except Exception:
            logger.exception("Tutorial branch could not be built: %s", step.title)
            return

        if branch is None or not branch.steps:
            logger.debug("Tutorial branch for '%s' is empty", step.title)
            return

        logger.info("Entering tutorial branch '%s' (%d steps)", branch.title, len(branch.steps))
        self.branch = branch
        self.branch_index = 0
        self.branch_origin = self.index
        self.apply_step()

    def exit_branch(self) -> None:
        """
        Leave the current branch and resume the main tour after it.

        The branch's cleanup always runs, whether the reader saw every
        step or turned back early, so a branch that opened a dialog can be
        relied on to close it.

        Returns:
            None
        """
        if self.branch is None:
            return

        branch, self.branch = self.branch, None
        logger.info("Leaving tutorial branch '%s'", branch.title)

        if branch.cleanup is not None:
            try:
                branch.cleanup()
            except Exception:
                logger.exception("Tutorial branch cleanup failed: %s", branch.title)

        origin = self.steps[self.branch_origin]
        self.run_after(origin)

        if self.branch_origin >= len(self.steps) - 1:
            self.stop(completed=True)
            return

        self.index = self.branch_origin + 1
        self.apply_step()

    # ----- NAVIGATION -----

    def go_next(self) -> None:
        """
        Advance one step, leaving the branch or finishing the tour at the end.

        Returns:
            None
        """
        if not self.active:
            return

        if self.branch is not None:
            self.run_after(self.current_step())

            if self.branch_index >= len(self.branch.steps) - 1:
                self.exit_branch()
                return

            self.branch_index += 1
            self.apply_step()
            return

        self.run_after(self.current_step())

        if self.index >= len(self.steps) - 1:
            self.stop(completed=True)
            return

        self.index += 1
        self.apply_step()

    def go_back(self) -> None:
        """
        Return to the previous step, leaving the branch at its first step.

        Returns:
            None
        """
        if not self.active:
            return

        if self.branch is not None:
            if self.branch_index == 0:
                self.return_to_origin()
                return

            self.branch_index -= 1
            self.apply_step()
            return

        if self.index == 0:
            return

        self.index -= 1
        self.apply_step()

    def return_to_origin(self) -> None:
        """
        Abandon the branch and go back to the step that offered it.

        Used by Back on the first branch step, where moving on to the next
        main step would skip content the reader hasn't seen.

        Returns:
            None
        """
        branch, self.branch = self.branch, None

        if branch is not None and branch.cleanup is not None:
            try:
                branch.cleanup()
            except Exception:
                logger.exception("Tutorial branch cleanup failed: %s", branch.title)

        self.index = self.branch_origin
        self.apply_step()

    def quit_tour(self) -> None:
        """
        End the tour from anywhere, including from inside a branch.

        Returns:
            None
        """
        if not self.active:
            return

        logger.info("Tutorial closed at step %d", self.index + 1)
        self.stop(completed=False)

    def skip(self) -> None:
        """
        Leave the current branch, or end the tour when on the main tour.

        Returns:
            None
        """
        if not self.active:
            return

        if self.branch is not None:
            self.exit_branch()
            return

        logger.info("Tutorial skipped at step %d", self.index + 1)
        self.stop(completed=False)

    def stop(self, completed: bool) -> None:
        """
        Tear down the overlay and report the outcome.

        Args:
            completed (bool): True when every step was viewed.

        Returns:
            None
        """
        if not self.active:
            return

        self.active = False

        # A tour ended from inside a branch still owes that branch its
        # cleanup, or a dialog it opened would be left on screen
        branch, self.branch = self.branch, None
        if branch is not None and branch.cleanup is not None:
            try:
                branch.cleanup()
            except Exception:
                logger.exception("Tutorial branch cleanup failed: %s", branch.title)

        from ui.theme_manager import ThemeManager
        tm = ThemeManager.get_instance()
        if tm:
            try:
                tm.themeChanged.disconnect(self.refresh_step)
            except (RuntimeError, TypeError):
                pass

        if self.overlay is not None:
            self.overlay.teardown()
            self.overlay = None

        logger.info("Tutorial finished (completed=%s)", completed)
        self.finished.emit(completed)
