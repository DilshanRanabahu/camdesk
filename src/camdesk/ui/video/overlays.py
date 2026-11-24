"""Overlays drawn as separate child widgets on top of the VideoWidget (never in its GL paint)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraFacing
from camdesk.core.state import AppState
from camdesk.ui import strings
from camdesk.ui.theme import tokens
from camdesk.utils.timing import CpuMeter

REFRESH_MS = 500


def _mono_font() -> QFont:
    font = QFont(tokens.FONT_MONO)
    font.setFamilies([tokens.FONT_MONO, tokens.FONT_MONO_FALLBACK])
    font.setPixelSize(tokens.SIZE_MONO)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class DebugOverlay(QLabel):
    """Ctrl+D panel: render/stream FPS, decoder, bitrate, frame age, dropped frames, CPU."""

    def __init__(self, video: QWidget, buffer: LatestFrameBuffer, state: AppState) -> None:
        super().__init__(video)
        self._video = video
        self._buffer = buffer
        self._state = state
        self._cpu = CpuMeter()
        self.setFont(_mono_font())
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            f"background:{tokens.BG_OVERLAY}; color:{tokens.TEXT_PRIMARY};"
            f"border-radius:{tokens.RADIUS_SM}px; padding:{tokens.SPACE_2}px {tokens.SPACE_3}px;"
        )
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self.hide()

    def toggle(self) -> None:
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self._cpu.sample()  # start a fresh measurement window
            self._timer.start()
            self.refresh()
        else:
            self._timer.stop()

    def refresh(self) -> None:
        none = strings.DEBUG_NO_DATA
        info = self._state.stream_info
        cam = self._state.camera_status
        caps = self._state.capabilities
        video = self._video
        render_fps = getattr(video, "render_fps", None)
        age = getattr(video, "last_frame_age_ms", None)
        one_core, whole = self._cpu.sample()
        lines = [
            strings.DEBUG_TITLE,
            f"{strings.DEBUG_RENDER_FPS:<10}{render_fps.rate:5.1f} fps" if render_fps else none,
            f"{strings.DEBUG_STREAM_FPS:<10}{info.fps:5.1f} fps"
            if info.fps
            else f"{strings.DEBUG_STREAM_FPS:<10}{none}",
            f"{strings.DEBUG_RESOLUTION:<10}{info.width}×{info.height}"
            if info.width
            else f"{strings.DEBUG_RESOLUTION:<10}{none}",
            f"{strings.DEBUG_DECODER:<10}{info.decoder or none}",
            f"{strings.DEBUG_TRANSPORT:<10}{info.transport or none}",
            f"{strings.DEBUG_BITRATE:<10}{info.bitrate_kbps / 1000:.1f} Mbps"
            if info.bitrate_kbps
            else f"{strings.DEBUG_BITRATE:<10}{none}",
            f"{strings.DEBUG_FRAME_AGE:<10}{age:5.1f} ms"
            if age is not None
            else f"{strings.DEBUG_FRAME_AGE:<10}{none}",
            f"{strings.DEBUG_DROPPED:<10}{self._buffer.dropped}",
            f"{strings.DEBUG_CPU:<10}{whole:4.1f}%  ({one_core:.0f}% of 1 core)",
            "",
            f"{strings.DEBUG_CAMERA:<10}"
            + (strings.DEBUG_FRONT if cam.facing is CameraFacing.FRONT else strings.DEBUG_BACK)
            + f" · {cam.zoom_ratio:.1f}× (max {caps.zoom_max_ratio:.0f}×)",
            f"{strings.DEBUG_TORCH:<10}"
            + (strings.DEBUG_ON if cam.torch else strings.DEBUG_OFF)
            + ("" if caps.has_torch else f" ({strings.DEBUG_UNAVAILABLE})"),
            f"{strings.DEBUG_NIGHT:<10}"
            + (strings.DEBUG_ON if cam.night_vision else strings.DEBUG_OFF),
            f"{strings.DEBUG_PHONE:<10}{cam.video_size or none} · q{cam.quality}",
        ]
        self.setText("\n".join(lines))
        self.adjustSize()
        margin = tokens.SPACE_3
        self.move(video.width() - self.width() - margin, margin)
