"""Turn IP Webcam's status.json / sensors.json into CamDesk models.

Parsing is lenient: missing or odd fields fall back to safe defaults instead of failing,
because field details differ between IP Webcam versions and phones.
"""

from __future__ import annotations

import logging
from typing import Any

from camdesk.camera import endpoints as ep
from camdesk.core.models import CameraCapabilities, CameraFacing, CameraStatus, DeviceInfo

log = logging.getLogger(__name__)

# IP Webcam's /ptz zoom is 0–100 and doesn't report the phone's max ratio.
# 10× is common on Android phones (and confirmed on the Galaxy A06 via ADB).
DEFAULT_ZOOM_MAX_RATIO = 10.0

_AUTOFOCUS_MODES = {"auto", "macro", "continuous-video", "continuous-picture", "edof"}
_TORCH_MODES = {"torch", "on"}


def _on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"on", "true", "1", "yes"}


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _str_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    return ()


def parse_status(data: dict[str, Any]) -> CameraStatus:
    cur = data.get(ep.CURVALS) or {}
    return CameraStatus(
        facing=CameraFacing.FRONT if _on(cur.get(ep.KEY_FRONT_CAMERA)) else CameraFacing.BACK,
        torch=_on(cur.get("torch")),
        night_vision=_on(cur.get(ep.KEY_NIGHT_VISION)),
        focus=_on(cur.get("focus")),
        zoom_percent=max(0, min(100, _int(cur.get("zoom"), 0))),
        quality=_int(cur.get(ep.KEY_QUALITY), 50),
        exposure=_int(cur.get(ep.KEY_EXPOSURE), 0),
        video_size=str(cur.get(ep.KEY_VIDEO_SIZE, "")),
        orientation=str(cur.get(ep.KEY_ORIENTATION, "landscape")),
    )


def parse_capabilities(data: dict[str, Any]) -> CameraCapabilities:
    cur = data.get(ep.CURVALS) or {}
    avail = data.get(ep.AVAIL) or {}
    front = _on(cur.get(ep.KEY_FRONT_CAMERA))

    if "flashmode" in avail:
        has_torch = bool(_TORCH_MODES & {m.lower() for m in _str_list(avail["flashmode"])})
    else:
        has_torch = not front  # front cameras rarely have a flash

    if "focusmode" in avail:
        modes = {m.lower() for m in _str_list(avail["focusmode"])}
        has_autofocus = bool(_AUTOFOCUS_MODES & modes)
    else:
        has_autofocus = not front

    exposure = [_int(v, 0) for v in _str_list(avail.get(ep.KEY_EXPOSURE))]
    exp_min, exp_max = (min(exposure), max(exposure)) if exposure else (0, 0)

    return CameraCapabilities(
        has_torch=has_torch,
        has_autofocus=has_autofocus,
        has_front_camera=ep.KEY_FRONT_CAMERA in avail or ep.KEY_FRONT_CAMERA in cur,
        has_night_vision=ep.KEY_NIGHT_VISION in cur,
        zoom_max_ratio=DEFAULT_ZOOM_MAX_RATIO if "zoom" in cur else 1.0,
        exposure_min=exp_min,
        exposure_max=exp_max,
        video_sizes=_str_list(avail.get(ep.KEY_VIDEO_SIZE)),
        orientations=_str_list(avail.get(ep.KEY_ORIENTATION)),
    )


def _latest_sensor_value(data: dict[str, Any], key: str) -> float | None:
    """sensors.json format: {key: {"data": [[timestamp, [value, ...]], ...]}}."""
    try:
        return float(data[key]["data"][-1][1][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_sensors(data: dict[str, Any]) -> DeviceInfo:
    level = _latest_sensor_value(data, ep.SENSOR_BATTERY_LEVEL)
    charging = _latest_sensor_value(data, ep.SENSOR_BATTERY_CHARGING)
    return DeviceInfo(
        battery_percent=level,
        charging=None if charging is None else charging > 0,
    )
