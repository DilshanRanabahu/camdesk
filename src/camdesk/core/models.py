"""Plain data models shared across layers. No Qt widgets, no I/O."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto

DEFAULT_PORT = 8080


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class CameraProfile:
    """A saved phone camera. The password is stored in keyring, never here."""

    name: str
    host: str
    port: int = DEFAULT_PORT
    username: str = ""
    id: str = field(default_factory=new_id)

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class ConnectionState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    FAILED = auto()


class CameraFacing(Enum):
    BACK = "back"
    FRONT = "front"


@dataclass(frozen=True, slots=True)
class CameraCapabilities:
    """What the active camera supports. Drives which controls are enabled."""

    has_torch: bool = False
    has_autofocus: bool = False
    has_front_camera: bool = False
    has_night_vision: bool = False
    zoom_max_ratio: float = 1.0  # zoom percent 100 maps to this ratio (e.g. 10.0 -> "10×")
    exposure_min: int = 0
    exposure_max: int = 0
    video_sizes: tuple[str, ...] = ()
    orientations: tuple[str, ...] = ()

    @property
    def has_zoom(self) -> bool:
        return self.zoom_max_ratio > 1.0

    @property
    def has_exposure(self) -> bool:
        return self.exposure_max > self.exposure_min

    def zoom_ratio(self, percent: int) -> float:
        """Map IP Webcam's 0–100 zoom value to a display ratio (1.0× … zoom_max_ratio×)."""
        p = max(0, min(100, percent))
        return 1.0 + (self.zoom_max_ratio - 1.0) * p / 100

    def zoom_percent(self, ratio: float) -> int:
        if not self.has_zoom:
            return 0
        p = (ratio - 1.0) / (self.zoom_max_ratio - 1.0) * 100
        return round(max(0.0, min(100.0, p)))


@dataclass(frozen=True, slots=True)
class CameraStatus:
    """Current camera settings as reported by the phone."""

    facing: CameraFacing = CameraFacing.BACK
    torch: bool = False
    night_vision: bool = False
    focus: bool = False
    zoom_percent: int = 0  # 0–100, as IP Webcam reports it
    quality: int = 50
    exposure: int = 0
    video_size: str = ""
    orientation: str = "landscape"


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    battery_percent: float | None = None
    charging: bool | None = None


@dataclass(frozen=True, slots=True)
class StreamInfo:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    latency_ms: float | None = None
    bitrate_kbps: float | None = None
    decoder: str = ""
    transport: str = ""  # "rtsp" or "mjpeg"


@dataclass(frozen=True, slots=True)
class RecordingState:
    active: bool = False
    elapsed_s: float = 0.0
    part: int = 1
    path: str = ""


class ToastLevel(Enum):
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class Toast:
    message: str
    level: ToastLevel = ToastLevel.INFO
    action_label: str = ""
    action_path: str = ""  # e.g. a folder/file to open when the action is clicked
