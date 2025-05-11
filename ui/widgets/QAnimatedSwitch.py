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
                 text_font: QFont = QFont,
                 parent=None) -> QWidget:
        super().__init__(parent)
        self.objectName = objectName
        self.on_text = on_text
        self.off_text = off_text
        self.checked_color = checked_color
        self.background_color = background_color
        self.text_position = text_position.lower()
        self.text_font = text_font
        self.toggled = False
        self.disabled = False
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.widgets()

    def widgets(self) -> None:
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.toggle_button = AnimatedToggle(checked_color=self.checked_color)
        self.toggle_button.setFocusPolicy(Qt.NoFocus)
        self.toggle_button.setFixedSize(QSize(50, 35))
        self.toggle_button.stateChanged.connect(self._on_toggled)
        layout.addWidget(self.toggle_button, 0, 0, 1, 1, Qt.AlignLeft)

        self.label = QLabel(text=self.off_text)
        if self.text_font:
            self.label.setFont(self.text_font)
        self.label.setFocusPolicy(Qt.NoFocus)
        self.label.mousePressEvent = self.handle_mouse_press
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.label, 0, 1, 1, 1, Qt.AlignLeft)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build_widgets()

        if self.background_color:
            self.setStyleSheet('QWidget {background-color: ' + self.background_color + '}')

    def _build_widgets(self):
        if self.layout():
            QWidget().setLayout(self.layout())

        layout = QGridLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)

        self.toggle_button = AnimatedToggle(checked_color=self.checked_color)
        self.toggle_button.setFixedSize(QSize(50, 35))
        self.toggle_button.stateChanged.connect(self._on_toggled)

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

    def handle_mouse_press(self, 
                           event: QMouseEvent) -> None:
        self.toggle(True)

    def toggle(self, 
               state: bool = True) -> None:
        if state:
            self.toggle_button.toggle()

    def setChecked(self, state: bool) -> None:
        if state != self.isChecked():
            self.toggle_button.toggle()
            
    def isChecked(self) -> None:
        return self.toggled

    def enable(self, 
               activate: bool) -> None:
        if activate:
            self.disabled = False
        else:
            self.disabled = True

    def isEnabled(self):
        return not self.disabled

    def disable(self, 
                activate: bool) -> None:
        if activate:
            self.disabled = True
        else:
            self.disabled = False

    def isDisabled(self) -> None:
        return self.disabled

    def hide(self):
        self.setVisible(False)
    def show(self):
        self.setVisible(True)

    def setWidth(self, width: int = 60):
        self.toggle_button.setWidth(width)

    def _on_toggled(self, 
                    checked: bool) -> None:
        self.toggled = not self.toggled
        self.label.setText(self.on_text if checked else self.off_text)
        self.stateChanged.emit(checked)
       
    def setCheckedColor(self) -> None:
        pass


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
        return QSize(58, 45)

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)

    def paintEvent(self, e: QPaintEvent):

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
        self._handle_position = 1 if value else 0

    @Property(float)
    def handle_position(self):
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos):
        """change the property
        we need to trigger QWidget.update() method, either by:
            1- calling it here [ what we're doing ].
            2- connecting the QPropertyAnimation.valueChanged() signal to it.
        """
        self._handle_position = pos
        self.update()

    @Property(float)
    def pulse_radius(self):
        return self._pulse_radius

    @pulse_radius.setter
    def pulse_radius(self, pos):
        self._pulse_radius = pos
        self.update()



class AnimatedToggle(Toggle):

    _transparent_pen = QPen(Qt.transparent)
    _light_grey_pen = QPen(Qt.lightGray)

    def __init__(self, *args, pulse_unchecked_color="#44999999",
        pulse_checked_color="#4400B0EE", **kwargs):

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
        self.animations_group.stop()
        if value:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animations_group.start()

    def paintEvent(self, e: QPaintEvent):

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