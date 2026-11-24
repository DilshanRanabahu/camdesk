"""Side panel (ui-design.md §5): Camera · Image · View cards.

Controls call AppController; AppState updates flow back in with `*_silently` setters, so a
value coming from the phone never re-sends a command. Controls the active camera can't use
are disabled with a "Not available on this camera" tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from camdesk.core.controller import AppController
from camdesk.core.models import CameraCapabilities, CameraStatus
from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens
from camdesk.ui.video.video_widget import ViewMode
from camdesk.ui.widgets.card import Card, row
from camdesk.ui.widgets.slider import LabeledSlider
from camdesk.ui.widgets.toggle import ToggleSwitch

ZOOM_STEPS_PER_X = 10  # slider works in tenths: 10 = 1.0×, 25 = 2.5×


def _icon_button(name: str, tip: str) -> QPushButton:
    button = QPushButton()
    button.setProperty("variant", "icon")
    button.setIcon(icons.icon(name, tokens.ICON_MD))
    button.setIconSize(icons.icon_size(tokens.ICON_MD))
    button.setToolTip(tip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class SidePanel(QScrollArea):
    view_mode_selected = Signal(object)  # ViewMode
    open_snapshots_requested = Signal()
    open_recordings_requested = Signal()

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self.setFixedWidth(tokens.SIDE_PANEL_WIDTH)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._c = controller
        self._caps = CameraCapabilities()
        self._connected = False

        body = QWidget()
        body.setObjectName("SidePanelBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(tokens.SPACE_3, tokens.SPACE_3, tokens.SPACE_3, tokens.SPACE_3)
        layout.setSpacing(tokens.SPACE_3)
        layout.addWidget(self._camera_card())
        layout.addWidget(self._image_card())
        layout.addWidget(self._view_card())
        layout.addWidget(self._captures_card())
        layout.addStretch(1)
        self.setWidget(body)
        self._apply_enabled()

    # -- cards ---------------------------------------------------------------

    def _camera_card(self) -> Card:
        card = Card(strings.PANEL_CAMERA)
        self.torch = ToggleSwitch()
        self.torch.toggled.connect(self._c.set_torch)
        self.torch_row = card.add(row(strings.FLASHLIGHT, self.torch, "flashlight"))
        self.night = ToggleSwitch()
        self.night.toggled.connect(self._c.set_night_vision)
        self.night_row = card.add(row(strings.NIGHT_VISION, self.night, "moon"))
        self.zoom = LabeledSlider(
            strings.ZOOM,
            ZOOM_STEPS_PER_X,
            ZOOM_STEPS_PER_X,
            lambda v: strings.ZOOM_VALUE.format(ratio=v / ZOOM_STEPS_PER_X),
        )
        self.zoom.value_changed.connect(lambda v: self._c.set_zoom(v / ZOOM_STEPS_PER_X))
        card.add(self.zoom)
        return card

    def _image_card(self) -> Card:
        card = Card(strings.PANEL_IMAGE)
        self.quality = LabeledSlider(
            strings.QUALITY, 1, 100, lambda v: strings.QUALITY_VALUE.format(value=v)
        )
        # Commit on release only: each change restarts the phone's encoder.
        self.quality.value_committed.connect(self._c.set_quality)
        card.add(self.quality)

        self.resolution = QComboBox()
        self.resolution.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.resolution.setMinimumContentsLength(len("1920x1080") + 1)
        self.resolution.activated.connect(
            lambda i: self._c.set_video_size(self.resolution.itemText(i))
        )
        card.add(row(strings.RESOLUTION, self.resolution))

        rotate = QWidget()
        rl = QHBoxLayout(rotate)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(tokens.SPACE_1)
        self.orientation_label = QLabel()
        self.orientation_label.setProperty("role", "secondary")
        self.rotate_left = _icon_button("rotate-ccw", strings.TIP_ROTATE_LEFT)
        self.rotate_right = _icon_button("rotate-cw", strings.TIP_ROTATE_RIGHT)
        self.rotate_left.clicked.connect(lambda: self._c.rotate(-1))
        self.rotate_right.clicked.connect(lambda: self._c.rotate(1))
        rl.addWidget(self.orientation_label)
        rl.addWidget(self.rotate_left)
        rl.addWidget(self.rotate_right)
        card.add(row(strings.ROTATE, rotate))

        self.mirror = ToggleSwitch()
        self.mirror.toggled.connect(lambda _: self._c.toggle_mirror())
        self.mirror_row = card.add(row(strings.MIRROR, self.mirror, "mirror"))
        self.flip = ToggleSwitch()
        self.flip.toggled.connect(lambda _: self._c.toggle_flip())
        self.flip_row = card.add(row(strings.FLIP, self.flip, "flip"))
        return card

    def _view_card(self) -> Card:
        card = Card(strings.PANEL_VIEW)
        segments = QWidget()
        segments.setToolTip(strings.TIP_VIEW)
        sl = QHBoxLayout(segments)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.view_group = QButtonGroup(self)
        self.view_buttons: dict[ViewMode, QPushButton] = {}
        for mode, text in (
            (ViewMode.FIT, strings.VIEW_FIT),
            (ViewMode.FILL, strings.VIEW_FILL),
            (ViewMode.ORIGINAL, strings.VIEW_ORIGINAL),
        ):
            button = QPushButton(text)
            button.setProperty("variant", "segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, m=mode: self.view_mode_selected.emit(m))
            self.view_group.addButton(button)
            self.view_buttons[mode] = button
            sl.addWidget(button, 1)
        self.view_buttons[ViewMode.FIT].setChecked(True)
        card.add(segments)
        return card

    def _captures_card(self) -> Card:
        card = Card(strings.PANEL_CAPTURES)
        for text, signal in (
            (strings.OPEN_SNAPSHOTS, self.open_snapshots_requested),
            (strings.OPEN_RECORDINGS, self.open_recordings_requested),
        ):
            button = QPushButton(text)
            button.setProperty("variant", "ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(signal)
            card.add(button)
        return card

    # -- AppState → widgets ----------------------------------------------------

    def update_status(self, s: CameraStatus) -> None:
        self.torch.set_checked_silently(s.torch)
        self.night.set_checked_silently(s.night_vision)
        self.zoom.set_value_silently(round(s.zoom_ratio * ZOOM_STEPS_PER_X))
        self.quality.set_value_silently(s.quality)
        self.mirror.set_checked_silently(s.mirrored)
        self.flip.set_checked_silently(s.flipped)
        self.orientation_label.setText(strings.ORIENTATION_NAMES.get(s.orientation, s.orientation))
        if s.video_size:
            index = self.resolution.findText(s.video_size)
            if index < 0:
                self.resolution.addItem(s.video_size)
                index = self.resolution.count() - 1
            self.resolution.blockSignals(True)
            self.resolution.setCurrentIndex(index)
            self.resolution.blockSignals(False)

    def update_capabilities(self, caps: CameraCapabilities) -> None:
        self._caps = caps
        self.zoom.set_range(ZOOM_STEPS_PER_X, round(caps.zoom_max_ratio * ZOOM_STEPS_PER_X))
        if caps.video_sizes:
            current = self.resolution.currentText()
            self.resolution.blockSignals(True)
            self.resolution.clear()
            self.resolution.addItems(list(caps.video_sizes))
            if current:
                self.resolution.setCurrentText(current)
            self.resolution.blockSignals(False)
        self._apply_enabled()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._apply_enabled()

    def set_view_mode(self, mode: ViewMode) -> None:
        self.view_buttons[mode].setChecked(True)

    def _apply_enabled(self) -> None:
        on, caps = self._connected, self._caps
        flips = caps.flip_modes or ("none", "mirror", "flip", "mirror,flip")
        for widget, row_widget, available in (
            (self.torch, self.torch_row, caps.has_torch),
            (self.night, self.night_row, caps.has_night_vision),
            (self.mirror, self.mirror_row, "mirror" in flips),
            (self.flip, self.flip_row, "flip" in flips),
        ):
            widget.setEnabled(on and available)
            row_widget.setEnabled(on and available)
            row_widget.setToolTip("" if available or not on else strings.NOT_ON_THIS_CAMERA)
        self.zoom.setEnabled(on and caps.has_zoom)
        self.zoom.setToolTip("" if caps.has_zoom or not on else strings.NOT_ON_THIS_CAMERA)
        for widget in (self.quality, self.resolution, self.rotate_left, self.rotate_right):
            widget.setEnabled(on)
