from __future__ import annotations

from PySide6.QtWidgets import QApplication

from camdesk.core.models import (
    CameraCapabilities,
    CameraProfile,
    CameraStatus,
    ConnectionState,
    DeviceInfo,
    StreamInfo,
)
from camdesk.core.state import AppState
from qt_helpers import SignalRecorder


def test_setters_emit_only_on_change(qapp: QApplication) -> None:
    state = AppState()
    status = SignalRecorder(state.camera_status_changed)
    state.set_camera_status(CameraStatus(torch=True))
    state.set_camera_status(CameraStatus(torch=True))  # same value again
    state.set_camera_status(CameraStatus(torch=False))
    assert status.count == 2

    info = SignalRecorder(state.stream_info_changed)
    state.set_stream_info(StreamInfo(fps=30.0))
    state.set_stream_info(StreamInfo(fps=30.0))
    assert info.count == 1


def test_connection_repeats_only_when_message_changes(qapp: QApplication) -> None:
    state = AppState()
    rec = SignalRecorder(state.connection_changed)
    state.set_connection(ConnectionState.RECONNECTING, "attempt 1")
    state.set_connection(ConnectionState.RECONNECTING, "attempt 1")
    state.set_connection(ConnectionState.RECONNECTING, "attempt 2")
    assert [c[1] for c in rec.calls] == ["attempt 1", "attempt 2"]


def test_none_capabilities_keep_previous(qapp: QApplication) -> None:
    state = AppState()
    caps = CameraCapabilities(has_torch=True, zoom_max_ratio=10.0)
    state.set_capabilities(caps)
    rec = SignalRecorder(state.capabilities_changed)
    state.set_capabilities(None)  # phone mid camera-switch
    assert state.capabilities == caps and rec.count == 0


def test_reset_camera_data(qapp: QApplication) -> None:
    state = AppState()
    state.set_camera(CameraProfile(name="A06", host="1.2.3.4"))
    state.set_camera_status(CameraStatus(torch=True))
    state.set_device_info(DeviceInfo(battery_percent=50))
    state.reset_camera_data()
    assert state.camera_status == CameraStatus()
    assert state.device_info == DeviceInfo()
    assert state.camera is not None  # the camera itself stays selected
