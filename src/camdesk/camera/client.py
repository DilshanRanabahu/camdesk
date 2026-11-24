"""Talking to the IP Webcam HTTP API.

`CameraApi`    — plain synchronous HTTP calls (easy to test, no Qt).
`CameraClient` — runs a CameraApi on its own QThread. Commands are queued and executed
                 in order; results come back as Qt signals. Never blocks the UI thread.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import shiboken6
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from camdesk.camera import capabilities as caps
from camdesk.camera import endpoints as ep
from camdesk.camera.endpoints import Command
from camdesk.core.errors import CameraAuthError, CameraError
from camdesk.core.models import CameraCapabilities, CameraStatus, DeviceInfo

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(3.0, connect=2.0)
POLL_INTERVAL_MS = 5_000


class CameraApi:
    """Synchronous IP Webcam API client. Not thread-safe; use one per thread."""

    def __init__(self, host: str, port: int, username: str = "", password: str = "") -> None:
        auth = httpx.BasicAuth(username, password) if (username or password) else None
        self.base_url = ep.http_base(host, port)
        self._http = httpx.Client(base_url=self.base_url, auth=auth, timeout=TIMEOUT)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: tuple[tuple[str, str], ...] = ()) -> httpx.Response:
        try:
            resp = self._http.get(path, params=params)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Windows retries refused connections for ~2 s, so a closed port is a timeout.
            raise CameraError("Can't reach the phone") from exc
        except httpx.TimeoutException as exc:
            raise CameraError("The phone did not respond in time") from exc
        except httpx.HTTPError as exc:
            raise CameraError("Can't reach the phone") from exc
        if resp.status_code == 401:
            raise CameraAuthError("Wrong username or password")
        if resp.status_code >= 400:
            raise CameraError(f"The phone rejected the request (HTTP {resp.status_code})")
        return resp

    def _json(self, path: str, params: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
        try:
            data = self._get(path, params).json()
        except ValueError as exc:
            raise CameraError("Unexpected reply from the phone — is this IP Webcam?") from exc
        if not isinstance(data, dict):
            raise CameraError("Unexpected reply from the phone — is this IP Webcam?")
        return data

    def status(self) -> tuple[CameraStatus, CameraCapabilities | None]:
        """Capabilities are None while the phone is mid camera-switch (keep the old ones)."""
        data = self._json(ep.STATUS, (("show_avail", "1"),))
        return caps.parse_status(data), caps.parse_capabilities(data)

    def sensors(self) -> DeviceInfo:
        return caps.parse_sensors(self._json(ep.SENSORS))

    def send(self, command: Command) -> None:
        self._get(command.path, command.params)


class _Worker(QObject):
    """Lives on the camera thread. All slots run there, one at a time, in order."""

    status_received = Signal(object, object)  # CameraStatus, CameraCapabilities | None
    device_info_received = Signal(object)  # DeviceInfo
    command_succeeded = Signal(object)  # Command
    command_failed = Signal(object, str)  # Command, message
    reachable_changed = Signal(bool, str)  # reachable, message
    auth_failed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._api: CameraApi | None = None
        self._reachable: bool | None = None
        self._timer: QTimer | None = None

    @Slot(str, int, str, str)
    def configure(self, host: str, port: int, username: str, password: str) -> None:
        self._close_api()
        self._reachable = None
        self._api = CameraApi(host, port, username, password)
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(POLL_INTERVAL_MS)
            self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    @Slot()
    def disconnect_camera(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._close_api()
        self._reachable = None

    @Slot()
    def refresh(self) -> None:
        if self._api is None:
            return
        try:
            status, capabilities = self._api.status()
            self._set_reachable(True, "")
            self.status_received.emit(status, capabilities)
            self.device_info_received.emit(self._api.sensors())
        except CameraAuthError as exc:
            self._set_reachable(False, str(exc))
            self.auth_failed.emit()
        except CameraError as exc:
            self._set_reachable(False, str(exc))

    @Slot(object)
    def execute(self, command: Command) -> None:
        if self._api is None:
            self.command_failed.emit(command, "Not connected")
            return
        try:
            self._api.send(command)
        except CameraError as exc:
            log.warning("%s failed: %s", command.label or command.path, exc)
            self.command_failed.emit(command, str(exc))
            return
        self.command_succeeded.emit(command)
        self.refresh()  # read back what the phone actually applied

    @Slot()
    def shutdown(self) -> None:
        """Runs on the worker thread: the poll timer must be deleted by the thread that owns it.

        Destroying it later from the UI thread (e.g. by garbage collection) makes Qt warn
        "Timers cannot be stopped from another thread" and can abort the process.
        """
        self.disconnect_camera()
        if self._timer is not None:
            self._timer.stop()
            shiboken6.delete(self._timer)
            self._timer = None

    def _set_reachable(self, reachable: bool, message: str) -> None:
        if reachable != self._reachable:
            self._reachable = reachable
            log.info("Camera %s%s", "reachable" if reachable else "unreachable: ", message)
            self.reachable_changed.emit(reachable, message)

    def _close_api(self) -> None:
        if self._api is not None:
            self._api.close()
            self._api = None


class CameraClient(QObject):
    """Thread-safe front door to the phone. Call from the UI thread; listen to signals.

    status_received(status, capabilities): capabilities is None when unchanged/unknown
    (the phone is switching camera) — keep using the previous value.
    """

    status_received = Signal(object, object)
    device_info_received = Signal(object)
    command_succeeded = Signal(object)
    command_failed = Signal(object, str)
    reachable_changed = Signal(bool, str)
    auth_failed = Signal()

    # Internal: cross-thread requests (queued because the worker lives on another thread).
    _configure_requested = Signal(str, int, str, str)
    _disconnect_requested = Signal()
    _refresh_requested = Signal()
    _execute_requested = Signal(object)
    _shutdown_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._thread.setObjectName("CameraClient")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)

        self._configure_requested.connect(self._worker.configure)
        self._disconnect_requested.connect(self._worker.disconnect_camera)
        self._refresh_requested.connect(self._worker.refresh)
        self._execute_requested.connect(self._worker.execute)
        # Blocking: close() must wait until the worker has cleaned up before the thread quits
        # (QThread.quit() may exit before a normally queued shutdown call ever runs).
        self._shutdown_requested.connect(
            self._worker.shutdown, Qt.ConnectionType.BlockingQueuedConnection
        )

        w = self._worker
        w.status_received.connect(self.status_received)
        w.device_info_received.connect(self.device_info_received)
        w.command_succeeded.connect(self.command_succeeded)
        w.command_failed.connect(self.command_failed)
        w.reachable_changed.connect(self.reachable_changed)
        w.auth_failed.connect(self.auth_failed)

        self._thread.start()

    def connect_to(self, host: str, port: int, username: str = "", password: str = "") -> None:
        self._configure_requested.emit(host, port, username, password)

    def disconnect_camera(self) -> None:
        self._disconnect_requested.emit()

    def refresh(self) -> None:
        self._refresh_requested.emit()

    def send(self, command: Command) -> None:
        self._execute_requested.emit(command)

    def close(self) -> None:
        """Stop the worker thread. Safe to call more than once."""
        if self._thread.isRunning():
            self._shutdown_requested.emit()
            self._thread.quit()
            self._thread.wait(3000)
