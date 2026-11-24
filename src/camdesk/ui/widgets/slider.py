"""Labeled slider (ui-design.md §7): title + value on one row, a thin slider below.

`value_changed` fires while dragging (for live things like zoom); `value_committed` fires
once when the user lets go or uses the keyboard (for settings that restart the phone's
encoder, like quality). State updates from the phone never fight an active drag.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from camdesk.ui.theme import tokens


class LabeledSlider(QWidget):
    value_changed = Signal(int)
    value_committed = Signal(int)

    def __init__(
        self,
        title: str,
        minimum: int,
        maximum: int,
        fmt: Callable[[int], str] = str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fmt = fmt
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_1)
        header = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setProperty("role", "label")
        self.value_label = QLabel()
        self.value_label.setProperty("role", "mono")
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.value_label)
        layout.addLayout(header)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderReleased.connect(lambda: self.value_committed.emit(self.slider.value()))
        self._on_changed(self.slider.value(), emit=False)

    def set_range(self, minimum: int, maximum: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(minimum, maximum)
        self.slider.blockSignals(False)
        self._on_changed(self.slider.value(), emit=False)

    def set_value_silently(self, value: int) -> None:
        if self.slider.isSliderDown():
            return  # the user is dragging: their value wins
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self._on_changed(self.slider.value(), emit=False)

    def value(self) -> int:
        return self.slider.value()

    def _on_changed(self, value: int, emit: bool = True) -> None:
        self.value_label.setText(self._fmt(value))
        if not emit:
            return
        self.value_changed.emit(value)
        if not self.slider.isSliderDown():  # keyboard / click on the groove
            self.value_committed.emit(value)
