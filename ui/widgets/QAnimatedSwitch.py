from PySide6.QtWidgets import QCheckBox, QWidget, QGridLayout, QLabel, QSizePolicy
from PySide6.QtGui import QPainter, QPen, QFont, QBrush, QColor, QIcon, QPaintEvent, QPainter, QMouseEvent
from PySide6.QtCore import Qt, QSize, QPoint, Slot, Property, QPointF, QRectF, QEasingCurve, QSequentialAnimationGroup, QPropertyAnimation, Signal

### Toggle and AnimatedToggle are part of qtWidgets, provided by Martin Fitzpatrick
class QAnimatedSwitch(QWidget):
    stateChanged = Signal(bool)

    def __init__(self,
                 objectName: str = '',
                 on_text: str = '', 
                 off_text: str = '', 
                 checked_color: str = '#9C0000',
                 background_color: str = '',
                 text_position: str = 'right',
                 text_font: QFont = QFont("Arial", 10),
                 toggle_size: QSize = QSize(50, 35),
                 start_state: str = "off",
                 parent=None) -> None:
        """
        Initialize the QAnimatedSwitch widget.

        Configures display text, colors, layout orientation, toggle size,
        initial state, and connects internal signals.

        Args:
            objectName (str): Object name identifier.
            on_text (str): Text displayed when enabled.
            off_text (str): Text displayed when disabled.
            checked_color (str): Color used when toggled on.
            background_color (str): Optional background color.
            text_position (str): Position of label relative to toggle.
            text_font (QFont): Font used for the label.
            toggle_size (QSize): Size of the toggle control.
            start_state (str): Initial state ("on" or "off").
            parent (Any): Optional parent widget.

        Returns:
            None
        """
        super().__init__(parent)
        self.objectName = objectName
        self.on_text = on_text
        self.off_text = off_text
        self.checked_color = checked_color
        self.background_color = background_color
        self.text_position = text_position.lower()
        self.text_font = text_font
        self.toggle_size = toggle_size
        self.start_state = (start_state.lower() == "on")    # store as bool

        self.toggled = False
        self.disabled = False
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.initUI()
        
        if self.start_state:
            self.toggle_button.blockSignals(True)
            self.toggle_button.setChecked(True)
            self.toggled = self.start_state
            self.label.setText(self.on_text if self.start_state else self.off_text)
            self.toggle_button.blockSignals(False)
            self.toggle_button.stateChanged.connect(self.on_toggled)

    def initUI(self) -> None:
        """
        Initialize the toggle switch layout and child widgets.

        Creates the toggle control and label, arranges them according
        to the specified text position, and applies background styling.

        Returns:
            None
        """
        if self.layout():
            QWidget().setLayout(self.layout())

        layout = QGridLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)

        self.toggle_button = AnimatedToggle(checked_color=self.checked_color)
        self.toggle_button.setFixedSize(self.toggle_size)
        self.toggle_button.stateChanged.connect(self.on_toggled)

        self.label = QLabel(self.off_text)
        if self.text_font:
            self.label.setFont(self.text_font)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.label.mousePressEvent = self.handle_mouse_press

        pos = self.text_position
        if pos == 'left':
            layout.addWidget(self.label,         0, 0, Qt.AlignVCenter)
            layout.addWidget(self.toggle_button, 0, 1, Qt.AlignVCenter | Qt.AlignLeft)
        elif pos == 'right':
            layout.addWidget(self.toggle_button, 0, 0, Qt.AlignVCenter)
            layout.addWidget(self.label,         0, 1, Qt.AlignVCenter| Qt.AlignLeft)
        elif pos == 'top':
            layout.addWidget(self.label,         0, 0, 1, 2, Qt.AlignHCenter)
            layout.addWidget(self.toggle_button, 1, 0, 1, 2, Qt.AlignHCenter)
        elif pos == 'bottom':
            layout.addWidget(self.toggle_button, 0, 0, 1, 2, Qt.AlignHCenter)
            layout.addWidget(self.label,         1, 0, 1, 2, Qt.AlignHCenter)
        else:
            layout.addWidget(self.toggle_button, 0, 0, Qt.AlignVCenter)
            layout.addWidget(self.label,         0, 1, Qt.AlignVCenter)

        self.setLayout(layout)
        if self.background_color:
            self.setStyleSheet('QWidget {background-color: ' + self.background_color + '}')

    def handle_mouse_press(self,
            event: QMouseEvent) -> None:
        """
        Handle mouse press events on the label.

        Triggers the toggle action when the label is clicked.

        Args:
            event (QMouseEvent): The mouse event.

        Returns:
            None
        """
        self.toggle(True)

    def toggle(self,
            state: bool = True) -> None:
        """
        Toggle the switch state.

        Args:
            state (bool): If True, toggles the internal button state.

        Returns:
            None
        """
        if state:
            self.toggle_button.toggle()

    def on_toggled(self,
            checked: bool) -> None:
        """
        Handle internal toggle state changes.

        Updates the displayed label text and emits the stateChanged signal.

        Args:
            checked (bool): The new checked state.

        Returns:
            None
        """
        self.toggled = checked
        self.label.setText(self.on_text if checked else self.off_text)
        self.stateChanged.emit(checked)

    def setChecked(self, state: bool) -> None:
        """
        Set the checked state of the toggle.

        Args:
            state (bool): Desired checked state.

        Returns:
            None
        """
        if state != self.isChecked():
            self.toggle_button.toggle()
            self.toggled = state
            
    def isChecked(self) -> bool:
        """
        Return the current checked state.

        Returns:
            bool: True if checked, otherwise False.
        """
        return self.toggled

    def enable(self, 
            activate: bool) -> None:
        """
        Enable or disable the toggle interaction.

        Args:
            activate (bool): If True, enables interaction; otherwise disables it.

        Returns:
            None
        """
        if activate:
            self.disabled = False
        else:
            self.disabled = True

    def isEnabled(self) -> bool:
        """
        Return whether the toggle is enabled.

        Returns:
            bool: True if enabled, otherwise False.
        """
        return not self.disabled

    def disable(self, 
            activate: bool) -> None:
        """
        Disable or enable the toggle interaction.

        Args:
            activate (bool): If True, disables interaction; otherwise enables it.

        Returns:
            None
        """ 
        if activate:
            self.disabled = True
        else:
            self.disabled = False

    def isDisabled(self) -> bool:
        """
        Return whether the toggle is disabled.

        Returns:
            bool: True if disabled, otherwise False.
        """
        return self.disabled

    def hide(self):
        """
        Hide the toggle widget.

        Returns:
            None
        """
        self.setVisible(False)

    def show(self):
        """
        Show the toggle widget.

        Returns:
            None
        """
        self.setVisible(True)

    def setWidth(self, width: int = 60):
        """
        Set the width of the internal toggle button.

        Args:
            width (int): Desired width.

        Returns:
            None
        """
        self.toggle_button.setWidth(width)
       
    def setCheckedColor(self) -> None:
        """
        Set the checked color of the toggle.

        Returns:
            None
        """
        #FIXME: Needs work
        pass

    def applyStyles(self):
        """
        Reapply styling and sizing to the toggle widget.

        Updates toggle size, font, background color, and refreshes layout.

        Returns:
            None
        """
        if self.toggle_size:
            self.toggle_button.setFixedSize(self.toggle_size)

        if self.text_font:
            self.label.setFont(self.text_font)

        if self.background_color:
            self.setStyleSheet('QWidget {background-color: ' + self.background_color + '}')

        # Need to be able to update checked color

        self.layout().invalidate()
        self.update()



### Toggle and Animated Toggle are part of qtWidgets, provided by Martin Fitzpatrick
class Toggle(QCheckBox):

    _transparent_pen = QPen(Qt.transparent)
    _light_grey_pen = QPen(Qt.lightGray)

    def __init__(self,
        parent=None,
        bar_color=Qt.gray,
        checked_color="#00B0FF",
        handle_color=Qt.white,
        ):
        """
        Initialize the Toggle widget.

        Configures brush colors for the bar and handle in both checked and
        unchecked states, sets layout margins, and connects state change handling.

        Args:
            parent (Any): Optional parent widget.
            bar_color (Any): Color of the toggle bar when unchecked.
            checked_color (str): Color used when the toggle is checked.
            handle_color (Any): Color of the toggle handle when unchecked.

        Returns:
            None
        """
        super().__init__(parent)

        # Save our properties on the object via self, so we can access them later
        # in the paintEvent.
        self._bar_brush = QBrush(bar_color)
        self._bar_checked_brush = QBrush(QColor(checked_color).lighter())

        self._handle_brush = QBrush(handle_color)
        self._handle_checked_brush = QBrush(QColor(checked_color))

        # Setup the rest of the widget.

        self.setContentsMargins(8, 0, 8, 0)
        self._handle_position = 0

        self.stateChanged.connect(self.handle_state_change)

    def sizeHint(self):
        """
        Return the recommended size for the widget.

        Returns:
            QSize: Suggested size for the toggle.
        """
        return QSize(58, 45)

    def hitButton(self, pos: QPoint):
        """
        Determine whether a position is within the clickable area.

        Args:
            pos (QPoint): Position to test.

        Returns:
            bool: True if the position is within the button area, otherwise False.
        """
        return self.contentsRect().contains(pos)

    def paintEvent(self, e: QPaintEvent):
        """
        Handle the paint event for the toggle.

        Draws the toggle bar and handle based on the current checked state
        and handle position.

        Args:
            e (QPaintEvent): The paint event.

        Returns:
            None
        """
        contRect = self.contentsRect()
        handleRadius = round(0.24 * contRect.height())

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.setPen(self._transparent_pen)
        barRect = QRectF(
            0, 0,
            contRect.width() - handleRadius, 0.40 * contRect.height()
        )
        barRect.moveCenter(contRect.center())
        rounding = barRect.height() / 2

        # the handle will move along this line
        trailLength = contRect.width() - 2 * handleRadius
        xPos = contRect.x() + handleRadius + trailLength * self._handle_position

        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)

        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        p.drawEllipse(
            QPointF(xPos, barRect.center().y()),
            handleRadius, handleRadius)

        p.end()

    @Slot(int)
    def handle_state_change(self, value):
        """
        Update handle position when the state changes.

        Args:
            value (int): The new state value.

        Returns:
            None
        """
        self._handle_position = 1 if value else 0

    @Property(float)
    def handle_position(self):
        """
        Get the current handle position.

        Returns:
            float: The current handle position.
        """
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos):
        """
        Set the handle position and trigger a repaint.

        Args:
            pos (float): New handle position.

        Returns:
            None
        """
        self._handle_position = pos
        self.update()

    @Property(float)
    def pulse_radius(self):
        """
        Get the current pulse radius.

        Returns:
            float: The current pulse radius.
        """
        return self._pulse_radius

    @pulse_radius.setter
    def pulse_radius(self, pos):
        """
        Get the current pulse radius.

        Returns:
            float: The current pulse radius.
        """
        self._pulse_radius = pos
        self.update()



class AnimatedToggle(Toggle):

    _transparent_pen = QPen(Qt.transparent)
    _light_grey_pen = QPen(Qt.lightGray)

    def __init__(self, *args, pulse_unchecked_color="#44999999",
        pulse_checked_color="#4400B0EE", **kwargs):
        """
        Initialize the AnimatedToggle widget.

        Sets up property animations for handle movement and pulse effects,
        and configures animation grouping and pulse colors.

        Args:
            *args (Any): Positional arguments passed to the base class.
            pulse_unchecked_color (str): Pulse color when unchecked.
            pulse_checked_color (str): Pulse color when checked.
            **kwargs (Any): Keyword arguments passed to the base class.

        Returns:
            None
        """
        self._pulse_radius = 0

        super().__init__(*args, **kwargs)

        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.setDuration(200)  # time in ms

        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius", self)
        self.pulse_anim.setDuration(350)  # time in ms
        self.pulse_anim.setStartValue(10)
        self.pulse_anim.setEndValue(20)

        self.animations_group = QSequentialAnimationGroup()
        self.animations_group.addAnimation(self.animation)
        self.animations_group.addAnimation(self.pulse_anim)

        self._pulse_unchecked_animation = QBrush(QColor(pulse_unchecked_color))
        self._pulse_checked_animation = QBrush(QColor(pulse_checked_color))

    @Slot(int)
    def handle_state_change(self, value):
        """
        Start animations in response to state changes.

        Stops any running animations, sets the target handle position,
        and begins the animation sequence.

        Args:
            value (int): The new state value.

        Returns:
            None
        """
        self.animations_group.stop()
        if value:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animations_group.start()

    def paintEvent(self, e: QPaintEvent):
        """
        Handle the paint event for the animated toggle.

        Draws the toggle bar, handle, and optional pulse animation
        based on the current state and animation progress.

        Args:
            e (QPaintEvent): The paint event.

        Returns:
            None
        """
        contRect = self.contentsRect()
        handleRadius = round(0.24 * contRect.height())

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.setPen(self._transparent_pen)
        barRect = QRectF(
            0, 0,
            contRect.width() - handleRadius, 0.40 * contRect.height()
        )
        barRect.moveCenter(contRect.center())
        rounding = barRect.height() / 2

        # the handle will move along this line
        trailLength = contRect.width() - 2 * handleRadius

        xPos = contRect.x() + handleRadius + trailLength * self._handle_position

        if self.pulse_anim.state() == QPropertyAnimation.Running:
            p.setBrush(
                self._pulse_checked_animation if
                self.isChecked() else self._pulse_unchecked_animation)
            p.drawEllipse(QPointF(xPos, barRect.center().y()),
                          self._pulse_radius, self._pulse_radius)

        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)

        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(barRect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        p.drawEllipse(
            QPointF(xPos, barRect.center().y()),
            handleRadius, handleRadius)

        p.end()
