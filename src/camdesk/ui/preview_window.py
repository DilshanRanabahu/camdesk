"""Temporary live-video window for build step 4 (replaced by MainWindow in step 6).

Video fills the window. Ctrl+D debug overlay, F11 / double-click fullscreen, Esc exits it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow

from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import ConnectionState, StreamInfo
from camdesk.ui import strings
from camdesk.ui.theme import tokens
from camdesk.ui.video.overlays import DebugOverlay
from camdesk.ui.video.video_widget import VideoWidget, ViewMode

_STATE_TEXT = {
    ConnectionState.IDLE: strings.IDLE,
    ConnectionState.CONNECTING: strings.CONNECTING,
    ConnectionState.CONNECTED: strings.CONNECTED,
    ConnectionState.RECONNECTING: strings.RECONNECTING,
    ConnectionState.FAILED: strings.FAILED,
}


class PreviewWindow(QMainWindow):
    def __init__(self, buffer: LatestFrameBuffer, camera_label: str) -> None:
        super().__init__()
        self._camera_label = camera_label
        self.video = VideoWidget(buffer, self)
        self.debug = DebugOverlay(self.video, buffer)
        self.setCentralWidget(self.video)
        self.setStyleSheet(f"QMainWindow {{ background: {tokens.BG_BASE}; }}")
        self.resize(1280, 760)
        self.set_state(ConnectionState.IDLE, "")

        self.video.double_clicked.connect(self.toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+D"), self, self.debug.toggle)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.exit_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_V), self, self.cycle_view_mode)

    def set_state(self, state: ConnectionState, message: str) -> None:
        text = _STATE_TEXT[state]
        if message and state in (ConnectionState.RECONNECTING, ConnectionState.FAILED):
            text = f"{text} {message}"
        self.setWindowTitle(f"{strings.APP_NAME} — {self._camera_label} — {text}")

    def set_stream_info(self, info: StreamInfo) -> None:
        self.debug.set_stream_info(info)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()

    def cycle_view_mode(self) -> None:
        modes = list(ViewMode)
        self.video.set_view_mode(modes[(modes.index(self.video.view_mode) + 1) % len(modes)])
