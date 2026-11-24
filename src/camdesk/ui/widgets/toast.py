"""Toasts (ui-design.md §7): bottom-center cards — icon · [thumbnail] · message · [Open] · ✕.

Auto-dismiss after 3 s (5 s with an action, 6 s for errors), fade in/out, at most 3 stacked.
The host sizes itself to its cards, so it never blocks clicks on the video around them.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from camdesk.core.models import Toast, ToastLevel
from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens

MAX_TOASTS = 3
DURATION_MS = 3000
DURATION_ACTION_MS = 5000
DURATION_ERROR_MS = 6000

_LEVEL_ICON = {
    ToastLevel.INFO: ("info", tokens.ACCENT),
    ToastLevel.SUCCESS: ("check-circle", tokens.SUCCESS),
    ToastLevel.WARNING: ("alert-triangle", tokens.WARNING),
    ToastLevel.ERROR: ("alert-circle", tokens.DANGER),
}


class ToastCard(QFrame):
    def __init__(self, toast: Toast, host: ToastHost) -> None:
        super().__init__(host)
        self.setObjectName("Toast")
        self.toast = toast
        self._host = host
        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_3, tokens.SPACE_2, tokens.SPACE_2, tokens.SPACE_2)
        layout.setSpacing(tokens.SPACE_3)

        name, color = _LEVEL_ICON[toast.level]
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap(name, tokens.ICON_MD, color))
        layout.addWidget(glyph)
        if isinstance(toast.thumbnail, QImage) and not toast.thumbnail.isNull():
            thumb = QLabel()
            thumb.setObjectName("ToastThumb")
            image = toast.thumbnail.scaledToHeight(
                tokens.TOAST_THUMB_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
            thumb.setPixmap(QPixmap.fromImage(image))
            layout.addWidget(thumb)
        self.label = QLabel(toast.message)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(tokens.TOAST_MAX_TEXT_WIDTH)
        layout.addWidget(self.label, 1)
        if toast.action_path:
            self.action = QPushButton(toast.action_label or strings.OPEN_LINK)
            self.action.setProperty("variant", "ghost")
            self.action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action.clicked.connect(self._open)
            layout.addWidget(self.action)
        close = QPushButton()
        close.setProperty("variant", "icon")
        close.setIcon(icons.icon("x-small", tokens.ICON_SM, tokens.TEXT_SECONDARY))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.dismiss)
        layout.addWidget(close)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(tokens.ANIM_BASE)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._closing = False

        duration = (
            DURATION_ERROR_MS
            if toast.level is ToastLevel.ERROR
            else DURATION_ACTION_MS
            if toast.action_path
            else DURATION_MS
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(duration)

    def fade_in(self) -> None:
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(lambda: self._host.remove(self))
        self._fade.start()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._timer.stop()  # hovering keeps it open
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        if not self._closing:
            self._timer.start(DURATION_MS)
        super().leaveEvent(event)  # type: ignore[arg-type]

    def _open(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.toast.action_path))
        self.dismiss()


class ToastHost(QWidget):
    """Lives over the window's content; MainWindow keeps it centered above the status bar."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(tokens.SPACE_2)
        self.cards: list[ToastCard] = []
        self.hide()

    def show_toast(self, toast: Toast) -> ToastCard:
        # Same message again (e.g. repeated warning): restart it instead of stacking copies.
        for card in self.cards:
            if card.toast.message == toast.message and not card._closing:
                card._timer.start()
                return card
        while len([c for c in self.cards if not c._closing]) >= MAX_TOASTS:
            oldest = next(c for c in self.cards if not c._closing)
            oldest.dismiss()
        card = ToastCard(toast, self)
        self.cards.append(card)
        self._layout.addWidget(card)
        self._relayout()
        card.fade_in()
        return card

    def remove(self, card: ToastCard) -> None:
        if card in self.cards:
            self.cards.remove(card)
            self._layout.removeWidget(card)
            card.deleteLater()
        self._relayout()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        # Above the status bar and the floating control dock, so neither gets covered.
        bottom_gap = tokens.STATUSBAR_HEIGHT + tokens.DOCK_BUTTON + 3 * tokens.SPACE_6
        y = parent.height() - self.height() - bottom_gap
        self.move(max(0, x), max(0, y))

    def _relayout(self) -> None:
        self.setVisible(bool(self.cards))
        if self.cards:
            # A new card only gets its stylesheet sizes (padding, 36 px buttons) once polished;
            # measuring before that squashed it. Polish first, and measure again next tick.
            for card in self.cards:
                card.ensurePolished()
                card.adjustSize()
            self._layout.activate()
            self.reposition()
            self.raise_()
            QTimer.singleShot(0, self.reposition)
