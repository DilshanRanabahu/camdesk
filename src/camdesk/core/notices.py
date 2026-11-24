"""Notices — turns AppState changes into the toasts a user should see.

Watches AppState only (no services): "Reconnected" after a drop, and a one-time low-battery
warning. Kept out of AppController so that stays small.
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from camdesk.core import messages
from camdesk.core.models import ConnectionState, DeviceInfo, Toast, ToastLevel
from camdesk.core.state import AppState

LOW_BATTERY_PERCENT = 20
BATTERY_RESET_PERCENT = 25  # warn again only after it climbs back above this


class Notices(QObject):
    def __init__(self, state: AppState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._was_lost = False
        self._battery_warned = False
        state.connection_changed.connect(self._on_connection)
        state.device_info_changed.connect(self._on_device_info)
        state.camera_changed.connect(self._on_camera_changed)

    def _on_camera_changed(self, _camera: object) -> None:
        self._was_lost = False
        self._battery_warned = False

    def _on_connection(self, state: ConnectionState, _message: str) -> None:
        if state in (ConnectionState.RECONNECTING, ConnectionState.FAILED):
            # Only a drop *after* we had video counts (not the first connect attempts).
            if self._state.stream_info.width or self._was_lost:
                self._was_lost = True
        elif state is ConnectionState.CONNECTED:
            if self._was_lost:
                self._state.notify(Toast(messages.RECONNECTED, ToastLevel.SUCCESS))
            self._was_lost = False
        elif state is ConnectionState.IDLE:
            self._was_lost = False

    def _on_device_info(self, info: DeviceInfo) -> None:
        level = info.battery_percent
        if level is None:
            return
        if level < LOW_BATTERY_PERCENT and not info.charging and not self._battery_warned:
            self._battery_warned = True
            self._state.notify(
                Toast(messages.BATTERY_LOW.format(percent=level), ToastLevel.WARNING)
            )
        elif level > BATTERY_RESET_PERCENT or info.charging:
            self._battery_warned = False
