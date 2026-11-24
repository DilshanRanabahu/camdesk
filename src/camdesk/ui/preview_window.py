"""Temporary live-video window (build steps 4–5), replaced by MainWindow in step 6.

Listens to AppState and calls AppController — the same contract the real UI will use.
Keys: Ctrl+D debug · F11/F/double-click fullscreen · Esc exit fullscreen · V view mode
Temporary camera keys until the buttons arrive in step 7:
T flashlight · C switch camera · + / - zoom · N night vision · A autofocus · Ctrl+R retry
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow

from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraProfile, ConnectionState, Toast
from camdesk.core.state import AppState
from camdesk.ui import strings
from camdesk.ui.theme import tokens
from camdesk.ui.video.overlays import DebugOverlay
from camdesk.ui.video.video_widget import VideoWidget, ViewMode

log = logging.getLogger(__name__)

_STATE_TEXT = {
    ConnectionState.IDLE: strings.IDLE,
    ConnectionState.CONNECTING: strings.CONNECTING,
    ConnectionState.CONNECTED: strings.CONNECTED,
    ConnectionState.RECONNECTING: strings.RECONNECTING,
    ConnectionState.FAILED: strings.FAILED,
}


class PreviewWindow(QMainWindow):
    def __init__(
        self, buffer: LatestFrameBuffer, state: AppState, controller: AppController
    ) -> None:
        super().__init__()
        self._state = state
        self._controller = controller
        self.video = VideoWidget(buffer, self)
        self.debug = DebugOverlay(self.video, buffer, state)
        self.setCentralWidget(self.video)
        self.setStyleSheet(f"QMainWindow {{ background: {tokens.BG_BASE}; }}")
        self.resize(1280, 760)

        state.frame_ready.connect(self.video.on_frame_ready)
        state.connection_changed.connect(self._update_title)
        state.camera_changed.connect(self._update_title)
        state.notification.connect(self._show_toast)
        self._update_title()

        self.video.double_clicked.connect(self.toggle_fullscreen)
        keys = {
            "Ctrl+D": self.debug.toggle,
            "F11": self.toggle_fullscreen,
            "F": self.toggle_fullscreen,
            "Esc": self.exit_fullscreen,
            "V": self.cycle_view_mode,
            "T": controller.toggle_torch,
            "C": controller.switch_camera,
            "+": controller.zoom_in,
            "=": controller.zoom_in,  # + without Shift
            "-": controller.zoom_out,
            "N": controller.toggle_night_vision,
            "A": controller.focus,
            "Ctrl+R": controller.retry,
        }
        for key, action in keys.items():
            QShortcut(QKeySequence(key), self, action)

    def _update_title(self, *_: object) -> None:
        camera: CameraProfile | None = self._state.camera
        label = f"{camera.name} · {camera.address}" if camera else strings.IDLE
        text = _STATE_TEXT[self._state.connection]
        message = self._state.connection_message
        if message and self._state.connection in (
            ConnectionState.RECONNECTING,
            ConnectionState.FAILED,
        ):
            text = f"{text} {message}"
        self.setWindowTitle(f"{strings.APP_NAME} — {label} — {text}")

    def _show_toast(self, toast: Toast) -> None:
        # Real toasts arrive in step 9; until then show messages in the log and the title bar.
        log.info("Notification: %s", toast.message)
        self.statusBar().showMessage(toast.message, 4000)

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
