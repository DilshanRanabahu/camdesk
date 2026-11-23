"""Turn IP Webcam's status.json / sensors.json into CamDesk models.

Field meanings were checked against IP Webcam 1.19 on a Galaxy A06 (2026-11-23):
- `curvals.zoom` is the ratio × 100 ("100" = 1.0×, "1000" = 10×); `avail.zoom` lists the steps.
- `avail.torch` is ["on","off"] when the camera has a flashlight, ["off"] when not.
  (`avail.flashmode` is NOT reliable: the front camera still lists "on".)
- `avail.focusmode` is ["off"] on a fixed-focus camera.
- While the phone switches camera (~2–3 s), `avail` is incomplete (no torch/focusmode/zoom).
  We return None then, so the app keeps the previous capabilities instead of flickering.

Parsing is lenient: odd values fall back to safe defaults instead of failing.
"""

from __future__ import annotations

import logging
from typing import Any

from camdesk.camera import endpoints as ep
from camdesk.core.models import CameraCapabilities, CameraFacing, CameraStatus, DeviceInfo

log = logging.getLogger(__name__)

ZOOM_UNIT = 100  # curvals.zoom / avail.zoom are ratio × 100

_AUTOFOCUS_MODES = {"auto", "macro", "continuous-video", "continuous-picture", "edof"}
_CAPABILITY_KEYS = ("torch", "focusmode", "zoom")  # all missing => phone is mid-switch


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


def _zoom_ratio(raw: Any) -> float:
    return max(1.0, _int(raw, ZOOM_UNIT) / ZOOM_UNIT)


def parse_status(data: dict[str, Any]) -> CameraStatus:
    cur = data.get(ep.CURVALS) or {}
    return CameraStatus(
        facing=CameraFacing.FRONT if _on(cur.get(ep.KEY_FRONT_CAMERA)) else CameraFacing.BACK,
        torch=_on(cur.get("torch")),
        night_vision=_on(cur.get(ep.KEY_NIGHT_VISION)),
        zoom_ratio=_zoom_ratio(cur.get("zoom")),
        quality=_int(cur.get(ep.KEY_QUALITY), 50),
        exposure=_int(cur.get(ep.KEY_EXPOSURE), 0),
        focus_mode=str(cur.get("focusmode", "")),
        video_size=str(cur.get(ep.KEY_VIDEO_SIZE, "")),
        orientation=str(cur.get(ep.KEY_ORIENTATION, "landscape")),
    )


def parse_capabilities(data: dict[str, Any]) -> CameraCapabilities | None:
    """Return None when the phone didn't report a complete set (e.g. while switching camera)."""
    cur = data.get(ep.CURVALS) or {}
    avail = data.get(ep.AVAIL)
    if not isinstance(avail, dict) or not any(k in avail for k in _CAPABILITY_KEYS):
        return None

    torch_modes = {m.lower() for m in _str_list(avail.get("torch"))}
    focus_modes = {m.lower() for m in _str_list(avail.get("focusmode"))}
    zoom_steps = [_int(v, ZOOM_UNIT) for v in _str_list(avail.get("zoom"))]
    exposure = [_int(v, 0) for v in _str_list(avail.get(ep.KEY_EXPOSURE))]

    return CameraCapabilities(
        has_torch="on" in torch_modes,
        has_autofocus=bool(_AUTOFOCUS_MODES & focus_modes),
        has_front_camera=ep.KEY_FRONT_CAMERA in avail,
        has_night_vision=ep.KEY_NIGHT_VISION in avail or ep.KEY_NIGHT_VISION in cur,
        zoom_max_ratio=max(1.0, max(zoom_steps) / ZOOM_UNIT) if zoom_steps else 1.0,
        exposure_min=min(exposure) if exposure else 0,
        exposure_max=max(exposure) if exposure else 0,
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
    """IP Webcam may return {} (sensors off) — then battery stays None and the UI hides it."""
    level = _latest_sensor_value(data, ep.SENSOR_BATTERY_LEVEL)
    charging = _latest_sensor_value(data, ep.SENSOR_BATTERY_CHARGING)
    return DeviceInfo(
        battery_percent=level,
        charging=None if charging is None else charging > 0,
    )
