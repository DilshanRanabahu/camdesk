"""Toggle switch (ui-design.md §7): 36×20, off = gray track, on = accent, knob slides 150 ms."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from camdesk.ui.theme import tokens

TRACK_W, TRACK_H = 36, 20
KNOB_MARGIN = 3


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(TRACK_W, TRACK_H)
        self._pos = 0.0  # 0 = off (left), 1 = on (right)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(TRACK_W, TRACK_H)

    def set_checked_silently(self, checked: bool) -> None:
        """Reflect state from the phone without emitting toggled (no command loop)."""
        if checked == self.isChecked():
            return
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.4)
        track = QColor(tokens.TOGGLE_OFF)
        if self.isChecked():
            track = QColor(tokens.ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, TRACK_W, TRACK_H), TRACK_H / 2, TRACK_H / 2)
        d = TRACK_H - 2 * KNOB_MARGIN
        x = KNOB_MARGIN + self._pos * (TRACK_W - d - 2 * KNOB_MARGIN)
        p.setBrush(QColor(tokens.TEXT_ON_ACCENT))
        p.drawEllipse(QRectF(x, KNOB_MARGIN, d, d))
        p.end()
