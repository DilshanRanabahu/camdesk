"""AppState — the single source of truth the UI listens to.

Setters emit only when the value really changes, so widgets never repaint for nothing.
Everything here runs on the UI thread (services reach it through queued signals).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from camdesk.core.models import (
    CameraCapabilities,
    CameraProfile,
    CameraStatus,
    ConnectionState,
    DeviceInfo,
    RecordingState,
    StreamInfo,
    Toast,
)


class AppState(QObject):
    camera_changed = Signal(object)  # CameraProfile | None
    connection_changed = Signal(object, str)  # ConnectionState, message
    stream_info_changed = Signal(object)  # StreamInfo
    camera_status_changed = Signal(object)  # CameraStatus
    capabilities_changed = Signal(object)  # CameraCapabilities
    device_info_changed = Signal(object)  # DeviceInfo
    recording_changed = Signal(object)  # RecordingState
    notification = Signal(object)  # Toast
    frame_ready = Signal()  # a new frame is waiting in the LatestFrameBuffer

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.camera: CameraProfile | None = None
        self.connection = ConnectionState.IDLE
        self.connection_message = ""
        self.stream_info = StreamInfo()
        self.camera_status = CameraStatus()
        self.capabilities = CameraCapabilities()
        self.device_info = DeviceInfo()
        self.recording = RecordingState()

    def set_camera(self, camera: CameraProfile | None) -> None:
        if camera != self.camera:
            self.camera = camera
            self.camera_changed.emit(camera)

    def set_connection(self, state: ConnectionState, message: str = "") -> None:
        # RECONNECTING repeats on purpose: the message carries the attempt number.
        if (state, message) != (self.connection, self.connection_message):
            self.connection, self.connection_message = state, message
            self.connection_changed.emit(state, message)

    def set_stream_info(self, info: StreamInfo) -> None:
        if info != self.stream_info:
            self.stream_info = info
            self.stream_info_changed.emit(info)

    def set_camera_status(self, status: CameraStatus) -> None:
        if status != self.camera_status:
            self.camera_status = status
            self.camera_status_changed.emit(status)

    def set_capabilities(self, capabilities: CameraCapabilities | None) -> None:
        """None means "unknown right now" (phone mid camera-switch): keep the previous value."""
        if capabilities is not None and capabilities != self.capabilities:
            self.capabilities = capabilities
            self.capabilities_changed.emit(capabilities)

    def set_device_info(self, info: DeviceInfo) -> None:
        if info != self.device_info:
            self.device_info = info
            self.device_info_changed.emit(info)

    def set_recording(self, recording: RecordingState) -> None:
        if recording != self.recording:
            self.recording = recording
            self.recording_changed.emit(recording)

    def notify(self, toast: Toast) -> None:
        self.notification.emit(toast)

    def reset_camera_data(self) -> None:
        """Forget everything about the previous camera (on disconnect / camera change)."""
        self.set_stream_info(StreamInfo())
        self.set_camera_status(CameraStatus())
        self.set_capabilities(CameraCapabilities())
        self.set_device_info(DeviceInfo())
