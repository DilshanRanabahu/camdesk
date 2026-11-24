"""AppController — every user action goes through here.

The UI calls these methods and listens to AppState; it never touches services directly.
Services are passed in (not created here), so tests can use fakes:

- `client`: a CameraClient (HTTP control, its own thread)
- `make_stream(profile, password)`: returns a new, not-yet-started StreamService
- `secrets`: get/set passwords (keyring in the app, a dict in tests)
- `save_settings(settings)`: writes settings.json (run on a worker thread)

Controls are optimistic: AppState updates at once, and the phone's next status report
(or a failure) corrects it.
"""

from __future__ import annotations

import copy
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from PySide6.QtCore import QObject, QTimer, Slot

from camdesk.camera import endpoints as ep
from camdesk.camera.endpoints import Command
from camdesk.config import secrets as keyring_secrets
from camdesk.config import settings as settings_store
from camdesk.config.settings import Settings
from camdesk.core import geometry, messages
from camdesk.core.capture_manager import CaptureManager
from camdesk.core.frames import VideoFrame
from camdesk.core.models import (
    CameraCapabilities,
    CameraFacing,
    CameraProfile,
    CameraStatus,
    ConnectionState,
    StreamInfo,
    Toast,
    ToastLevel,
)
from camdesk.core.notices import Notices
from camdesk.core.state import AppState

log = logging.getLogger(__name__)

ZOOM_THROTTLE_MS = 80  # at most ~12 zoom commands/s while a slider is dragged
ZOOM_STEP = 0.5  # +/- keys change zoom by 0.5×


class Secrets(Protocol):
    def get_password(self, camera_id: str) -> str: ...
    def set_password(self, camera_id: str, password: str) -> None: ...
    def delete_password(self, camera_id: str) -> None: ...


StreamFactory = Callable[[CameraProfile, str], Any]  # -> StreamService


class AppController(QObject):
    def __init__(
        self,
        state: AppState,
        settings: Settings,
        client: Any,
        make_stream: StreamFactory,
        *,
        secrets: Secrets = keyring_secrets,  # type: ignore[assignment]
        save_settings: Callable[[Settings], None] = settings_store.save,
        latest_frame: Callable[[], VideoFrame | None] = lambda: None,
        capture: CaptureManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.settings = settings
        self._client = client
        self._make_stream = make_stream
        self._secrets = secrets
        self._save_settings = save_settings
        self._stream: Any = None
        self._in_flight = 0  # commands sent, not yet answered
        self.capture = capture or CaptureManager(state, settings, latest_frame, parent=self)
        self.notices = Notices(state, parent=self)
        self._auth_warned = False

        self._zoom_pending: int | None = None
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(ZOOM_THROTTLE_MS)
        self._zoom_timer.timeout.connect(self._flush_zoom)

        client.status_received.connect(self._on_status)
        client.device_info_received.connect(state.set_device_info)
        client.command_failed.connect(self._on_command_failed)
        client.command_succeeded.connect(self._on_command_done)
        client.auth_failed.connect(self._on_auth_failed)

    # -- connection --------------------------------------------------------

    @property
    def camera(self) -> CameraProfile | None:
        return self.state.camera

    def connect_camera(
        self, profile: CameraProfile, password: str | None = None, *, remember: bool = True
    ) -> None:
        """Connect to a camera (replacing the current one). `password=None` uses the saved one."""
        self.disconnect()
        if password is None:
            password = self._secrets.get_password(profile.id) if profile.username else ""
        elif remember:
            self._secrets.set_password(profile.id, password)
        if remember:
            self.settings.upsert_camera(profile)
            self.save_settings()

        self._auth_warned = False
        self.state.set_camera(profile)
        self._client.connect_to(profile.host, profile.port, profile.username, password)
        stream = self._make_stream(profile, password)
        # Connect to methods of this QObject (not lambdas): Qt then queues the calls onto the
        # UI thread. A lambda would run on the stream thread and touch AppState from there.
        stream.state_changed.connect(self._on_stream_state)
        stream.stream_info_changed.connect(self._on_stream_info)
        stream.frame_ready.connect(self.state.frame_ready)
        self._stream = stream
        self.capture.attach_stream(stream)
        log.info("Connecting to %s (%s)", profile.name, profile.address)
        stream.start()

    def disconnect(self) -> None:
        """Stop streaming and polling. Returns at once — never waits on the network."""
        self.capture.detach_stream()  # finishes a running recording
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.frame_ready.disconnect(self.state.frame_ready)
            stream.stop(timeout_s=0)  # the stream thread finishes on its own
        self._client.disconnect_camera()
        self._zoom_timer.stop()
        self._zoom_pending = None
        self._in_flight = 0
        self.state.reset_camera_data()
        self.state.set_connection(ConnectionState.IDLE)

    def close_camera(self) -> None:
        """Disconnect and deselect the camera (the UI goes back to the connect screen)."""
        self.disconnect()
        self.state.set_camera(None)

    def forget_camera(self, camera_id: str) -> None:
        """Remove a saved camera and its password."""
        if self.camera is not None and self.camera.id == camera_id:
            self.close_camera()
        self.settings.remove_camera(camera_id)
        self._secrets.delete_password(camera_id)
        self.save_settings()

    def find_camera(self, host: str, port: int) -> CameraProfile | None:
        return next((c for c in self.settings.cameras if (c.host, c.port) == (host, port)), None)

    def retry(self) -> None:
        if self._stream is not None:
            self._stream.retry()
        self._client.refresh()

    def shutdown(self) -> None:
        """App exit: stop everything and save settings (blocking is fine here)."""
        self._zoom_timer.stop()
        self.capture.shutdown()  # complete the recording file before the stream stops
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
        self._client.close()
        try:
            self._save_settings(self.settings)
        except OSError as exc:
            log.error("Could not save settings: %s", exc)

    def save_settings(self) -> None:
        """Save a snapshot of the settings on a worker thread (no file I/O on the UI thread)."""
        snapshot = copy.deepcopy(self.settings)

        def work() -> None:
            try:
                self._save_settings(snapshot)
            except OSError as exc:
                log.error("Could not save settings: %s", exc)

        threading.Thread(target=work, name="SaveSettings", daemon=True).start()

    # -- camera controls ---------------------------------------------------

    @property
    def status(self) -> CameraStatus:
        return self.state.camera_status

    @property
    def capabilities(self) -> CameraCapabilities:
        return self.state.capabilities

    def set_torch(self, on: bool) -> None:
        if on and not self.capabilities.has_torch:
            self._not_available("Flashlight")
            return
        self._send(ep.torch(on), replace(self.status, torch=on))

    def toggle_torch(self) -> None:
        self.set_torch(not self.status.torch)

    def switch_camera(self) -> None:
        if not self.capabilities.has_front_camera:
            self._not_available("Switch camera")
            return
        to_front = self.status.facing is not CameraFacing.FRONT
        facing = CameraFacing.FRONT if to_front else CameraFacing.BACK
        # The phone turns the torch off and resets zoom when it switches camera.
        self._send(
            ep.front_camera(to_front),
            replace(self.status, facing=facing, torch=False, zoom_ratio=1.0),
        )

    def set_zoom(self, ratio: float) -> None:
        caps = self.capabilities
        if not caps.has_zoom or self.camera is None:
            return
        ratio = max(1.0, min(caps.zoom_max_ratio, ratio))
        self.state.set_camera_status(replace(self.status, zoom_ratio=ratio))
        self._zoom_pending = caps.zoom_percent(ratio)
        if not self._zoom_timer.isActive():
            self._flush_zoom()  # first change goes out at once; the rest are throttled

    def zoom_in(self) -> None:
        self.set_zoom(self.status.zoom_ratio + ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self.status.zoom_ratio - ZOOM_STEP)

    def focus(self) -> None:
        if not self.capabilities.has_autofocus:
            self._not_available("Focus")
            return
        self._send(ep.focus(True))

    def set_night_vision(self, on: bool) -> None:
        self._send(ep.night_vision(on), replace(self.status, night_vision=on))

    def toggle_night_vision(self) -> None:
        self.set_night_vision(not self.status.night_vision)

    def set_quality(self, percent: int) -> None:
        percent = max(1, min(100, int(percent)))
        self._send(ep.quality(percent), replace(self.status, quality=percent))

    def set_video_size(self, size: str) -> None:
        if self.capabilities.video_sizes and size not in self.capabilities.video_sizes:
            self._not_available(f"Resolution {size}")
            return
        self._send(ep.video_size(size), replace(self.status, video_size=size))

    def set_orientation(self, orientation: str) -> None:
        self._send(ep.orientation(orientation), replace(self.status, orientation=orientation))

    def rotate(self, steps: int = 1) -> None:
        """Quarter turns: +1 clockwise, -1 counter-clockwise. Done on the phone, so recordings
        come out rotated too (verified: portrait changes the stream to 1080×1920)."""
        current = self.status.orientation
        self.set_orientation(
            geometry.rotate_orientation(current, steps, self.capabilities.orientations)
        )

    def set_mirror_flip(self, value: str) -> None:
        modes = self.capabilities.flip_modes
        if modes and value not in modes:
            self._not_available("Mirror / flip")
            return
        self._send(ep.mirror_flip(value), replace(self.status, mirror_flip=value))

    def toggle_mirror(self) -> None:
        self.set_mirror_flip(geometry.toggle_flip_mode(self.status.mirror_flip, "mirror"))

    def toggle_flip(self) -> None:
        self.set_mirror_flip(geometry.toggle_flip_mode(self.status.mirror_flip, "flip"))

    def focus_at(self, nx: float, ny: float) -> None:
        """Tap-to-focus at a point of the shown picture (0–1, origin top-left)."""
        if not self.capabilities.has_autofocus:
            self._not_available("Focus")
            return
        if self.capabilities.has_focus_region:
            s = self.status
            x, y = geometry.focus_point(nx, ny, s.orientation, s.mirror_flip)
            self._send(ep.focus_region(x, y))
        self._send(ep.focus(True))

    # -- internals ---------------------------------------------------------

    def _send(self, command: Command, optimistic: CameraStatus | None = None) -> None:
        if self.camera is None:
            return
        if optimistic is not None:
            self.state.set_camera_status(optimistic)
        self._in_flight += 1
        self._client.send(command)

    def _flush_zoom(self) -> None:
        if self._zoom_pending is None:
            return
        percent, self._zoom_pending = self._zoom_pending, None
        self._in_flight += 1
        self._client.send(ep.zoom(percent))
        self._zoom_timer.start()

    def _not_available(self, label: str) -> None:
        self.state.notify(Toast(messages.NOT_AVAILABLE.format(label=label), ToastLevel.WARNING))

    def _on_status(self, status: CameraStatus, capabilities: CameraCapabilities | None) -> None:
        if self.camera is None:
            return  # late reply after disconnect
        if self._in_flight > 0:
            # A report taken before our command ran would undo the optimistic change, and the
            # next click would build on that stale value (found on the phone: fast Mirror +
            # Upside-down clicks left mirror on). The client refreshes after each command,
            # so a fresh report follows once the last one is done.
            return
        if self._zoom_pending is not None or self._zoom_timer.isActive():
            status = replace(status, zoom_ratio=self.status.zoom_ratio)  # don't fight the slider
        self.state.set_camera_status(status)
        self.state.set_capabilities(capabilities)

    def _on_command_done(self, command: Command) -> None:
        self._in_flight = max(0, self._in_flight - 1)

    def _on_command_failed(self, command: Command, reason: str) -> None:
        self._in_flight = max(0, self._in_flight - 1)
        label = command.label or command.path
        self.state.notify(
            Toast(messages.COMMAND_FAILED.format(label=label, reason=reason), ToastLevel.ERROR)
        )
        self._client.refresh()  # undo the optimistic change with the phone's real state

    def _on_auth_failed(self) -> None:
        if self._auth_warned or self.camera is None:
            return
        self._auth_warned = True
        self.state.notify(
            Toast(messages.WRONG_PASSWORD.format(camera=self.camera.name), ToastLevel.ERROR)
        )

    def _from_current_stream(self) -> bool:
        """False for late signals from a stream we already stopped."""
        return self._stream is not None and self.sender() is self._stream

    @Slot(object, str)
    def _on_stream_state(self, state: ConnectionState, message: str) -> None:
        if not self._from_current_stream():
            return
        self.state.set_connection(state, message)
        if state is ConnectionState.CONNECTED:
            self._client.refresh()

    @Slot(object)
    def _on_stream_info(self, info: StreamInfo) -> None:
        if self._from_current_stream():
            self.state.set_stream_info(info)
