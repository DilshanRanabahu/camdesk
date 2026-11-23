"""Every IP Webcam URL and setting key, in one place (AGENTS.md rule 5)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

# -- paths ---------------------------------------------------------------

STATUS = "/status.json"
SENSORS = "/sensors.json"
SHOT = "/shot.jpg"
MJPEG_VIDEO = "/video"
AUDIO_WAV = "/audio.wav"
RTSP_H264 = "/h264_ulaw.sdp"  # H.264 video + μ-law audio

# -- setting keys (used with /settings/<key>?set=<value>) ----------------

KEY_FRONT_CAMERA = "ffc"
KEY_NIGHT_VISION = "night_vision"
KEY_QUALITY = "quality"
KEY_VIDEO_SIZE = "video_size"
KEY_ORIENTATION = "orientation"
KEY_EXPOSURE = "exposure"

# -- status.json field names --------------------------------------------

CURVALS = "curvals"
AVAIL = "avail"
SENSOR_BATTERY_LEVEL = "battery_level"
SENSOR_BATTERY_CHARGING = "battery_charging"


def _onoff(on: bool) -> str:
    return "on" if on else "off"


@dataclass(frozen=True, slots=True)
class Command:
    """One HTTP GET to the phone. `label` is the user-facing name for error messages."""

    path: str
    params: tuple[tuple[str, str], ...] = ()
    label: str = ""


def torch(on: bool) -> Command:
    return Command("/enabletorch" if on else "/disabletorch", label="Flashlight")


def focus(on: bool) -> Command:
    return Command("/focus" if on else "/nofocus", label="Focus")


def zoom(percent: int) -> Command:
    return Command("/ptz", (("zoom", str(max(0, min(100, int(percent))))),), label="Zoom")


def setting(key: str, value: str, label: str = "") -> Command:
    return Command(f"/settings/{key}", (("set", value),), label=label or key)


def front_camera(on: bool) -> Command:
    return setting(KEY_FRONT_CAMERA, _onoff(on), "Switch camera")


def night_vision(on: bool) -> Command:
    return setting(KEY_NIGHT_VISION, _onoff(on), "Night vision")


def quality(percent: int) -> Command:
    return setting(KEY_QUALITY, str(max(1, min(100, int(percent)))), "Quality")


def video_size(size: str) -> Command:
    return setting(KEY_VIDEO_SIZE, size, "Resolution")


def orientation(value: str) -> Command:
    return setting(KEY_ORIENTATION, value, "Orientation")


def exposure(value: int) -> Command:
    return setting(KEY_EXPOSURE, str(int(value)), "Exposure")


# -- full URLs -----------------------------------------------------------


def http_base(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def rtsp_url(host: str, port: int, username: str = "", password: str = "") -> str:
    auth = ""
    if username or password:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return f"rtsp://{auth}{host}:{port}{RTSP_H264}"


def mjpeg_url(host: str, port: int) -> str:
    return f"{http_base(host, port)}{MJPEG_VIDEO}"
