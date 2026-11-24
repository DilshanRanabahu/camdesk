"""Floating control dock over the video (ui-design.md §5): Snapshot · Record · Switch · Focus ·
Fullscreen. Fades out after 3 s without mouse movement over the video; any movement brings it
back. It is a separate child widget, so its animation never touches the video's GL paint.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QPushButton, QWidget

from camdesk.core.models import CameraCapabilities
from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens


def dock_button(icon_name: str, tip: str) -> QPushButton:
    button = QPushButton()
    button.setProperty("variant", "dock")
    button.setIcon(icons.icon(icon_name, tokens.ICON_LG))
    button.setIconSize(icons.icon_size(tokens.ICON_LG))
    button.setToolTip(tip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


class ControlDock(QFrame):
    snapshot_requested = Signal()
    record_requested = Signal()
    switch_camera_requested = Signal()
    focus_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(self, video: QWidget) -> None:
        super().__init__(video)
        self.setObjectName("Dock")
        self._video = video
        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_1, tokens.SPACE_1, tokens.SPACE_1, tokens.SPACE_1)
        layout.setSpacing(tokens.SPACE_1)

        self.snapshot = dock_button("camera", strings.TIP_SNAPSHOT)
        self.record = dock_button("record", strings.TIP_RECORD)
        self.switch = dock_button("switch-camera", strings.TIP_SWITCH_CAMERA)
        self.focus = dock_button("focus", strings.TIP_FOCUS)
        self.fullscreen = dock_button("fullscreen", strings.TIP_FULLSCREEN)
        for button, signal in (
            (self.snapshot, self.snapshot_requested),
            (self.record, self.record_requested),
            (self.switch, self.switch_camera_requested),
            (self.focus, self.focus_requested),
            (self.fullscreen, self.fullscreen_requested),
        ):
            button.clicked.connect(signal)
            layout.addWidget(button)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(tokens.ANIM_BASE)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade.finished.connect(self._after_fade)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(tokens.DOCK_AUTO_HIDE_MS)
        self._idle.timeout.connect(self.fade_out)

        video.setMouseTracking(True)
        video.installEventFilter(self)
        self.adjustSize()
        self._place()

    # -- capability-aware enabling ---------------------------------------

    def set_recording(self, active: bool) -> None:
        self.record.setProperty("recording", "true" if active else "false")
        self.record.setToolTip(strings.TIP_STOP_RECORD if active else strings.TIP_RECORD)
        self.record.style().unpolish(self.record)
        self.record.style().polish(self.record)

    def set_capabilities(self, caps: CameraCapabilities, connected: bool) -> None:
        self.snapshot.setEnabled(connected)
        self.record.setEnabled(connected)
        self.switch.setEnabled(connected and caps.has_front_camera)
        self.focus.setEnabled(connected and caps.has_autofocus)
        self.focus.setToolTip(
            strings.TIP_FOCUS if caps.has_autofocus else strings.NOT_ON_THIS_CAMERA
        )

    # -- auto-hide ---------------------------------------------------------

    def wake(self) -> None:
        """Show (fade in) and restart the idle timer."""
        if not self.isVisible() or self._effect.opacity() < 1.0:
            self.show()
            self.raise_()
            self._fade.stop()
            self._fade.setStartValue(self._effect.opacity())
            self._fade.setEndValue(1.0)
            self._fade.start()
        self._idle.start()

    def fade_out(self) -> None:
        if self.underMouse():
            self._idle.start()  # don't vanish under the cursor
            return
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self) -> None:
        if self._effect.opacity() == 0.0:
            self.hide()

    def _place(self) -> None:
        video = self._video
        self.move(
            (video.width() - self.width()) // 2,
            video.height() - self.height() - tokens.SPACE_6,
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._video:
            if event.type() == QEvent.Type.Resize:
                self._place()
            elif event.type() in (QEvent.Type.MouseMove, QEvent.Type.Enter):
                self.wake()
        return False
