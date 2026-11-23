from __future__ import annotations

import pytest

from camdesk.camera import capabilities as caps
from camdesk.core.models import CameraCapabilities, CameraFacing
from camdesk.dev.fake_camera import FakeCamera

# Trimmed real reply from IP Webcam 1.19 on the Galaxy A06 (back camera, 2026-11-23).
REAL_BACK = {
    "curvals": {
        "orientation": "landscape",
        "quality": "49",
        "night_vision": "off",
        "video_size": "1920x1080",
        "ffc": "off",
        "zoom": "100",
        "focusmode": "continuous-video",
        "flashmode": "off",
        "torch": "off",
    },
    "avail": {
        "orientation": ["landscape", "portrait", "upsidedown", "upsidedown_portrait"],
        "night_vision": ["on", "off"],
        "video_size": ["1920x1080", "1920x864", "1280x720"],
        "ffc": ["on", "off"],
        "zoom": ["100", "109", "118", "991", "1000"],
        "focusmode": ["off", "auto", "macro", "continuous-video", "continuous-picture"],
        "flashmode": ["off", "auto", "on", "red-eye"],
        "torch": ["on", "off"],
    },
}

# Front camera: flashmode still lists "on", but torch says only "off".
REAL_FRONT_AVAIL = {
    **REAL_BACK["avail"],
    "torch": ["off"],
    "focusmode": ["off"],
}


def test_real_back_camera() -> None:
    c = caps.parse_capabilities(REAL_BACK)
    s = caps.parse_status(REAL_BACK)
    assert c is not None
    assert c.has_torch and c.has_autofocus and c.has_front_camera and c.has_night_vision
    assert c.zoom_max_ratio == pytest.approx(10.0)
    assert not c.has_exposure  # this phone/app version has no exposure compensation
    assert c.video_sizes[0] == "1920x1080"
    assert s.facing is CameraFacing.BACK
    assert s.zoom_ratio == pytest.approx(1.0)
    assert s.quality == 49
    assert s.focus_mode == "continuous-video"


def test_real_front_camera_ignores_flashmode() -> None:
    data = {"curvals": {**REAL_BACK["curvals"], "ffc": "on"}, "avail": REAL_FRONT_AVAIL}
    c = caps.parse_capabilities(data)
    assert c is not None
    assert not c.has_torch
    assert not c.has_autofocus
    assert caps.parse_status(data).facing is CameraFacing.FRONT


def test_incomplete_avail_while_switching_returns_none() -> None:
    data = {
        "curvals": {**REAL_BACK["curvals"], "ffc": "on"},
        "avail": {"video_size": ["1920x1080"], "ffc": ["on", "off"]},
    }
    assert caps.parse_capabilities(data) is None
    assert caps.parse_capabilities({"curvals": {}}) is None  # no avail at all


def test_zoom_value_is_ratio_times_100() -> None:
    assert caps.parse_status({"curvals": {"zoom": "550"}}).zoom_ratio == pytest.approx(5.5)
    assert caps.parse_status({"curvals": {"zoom": "1000"}}).zoom_ratio == pytest.approx(10.0)
    assert caps.parse_status({"curvals": {"zoom": "0"}}).zoom_ratio == pytest.approx(1.0)


def test_fake_matches_real_shape(fake_camera: FakeCamera) -> None:
    c = caps.parse_capabilities(fake_camera.status(show_avail=True))
    assert c is not None and c.has_torch and c.zoom_max_ratio == pytest.approx(10.0)
    fake_camera.state["ffc"] = "on"
    c = caps.parse_capabilities(fake_camera.status(show_avail=True))
    assert c is not None and not c.has_torch and not c.has_autofocus
    fake_camera.switching = True
    assert caps.parse_capabilities(fake_camera.status(show_avail=True)) is None


def test_missing_and_garbage_values_use_safe_defaults() -> None:
    s = caps.parse_status({"curvals": {"zoom": "abc", "quality": None}})
    assert s.zoom_ratio == pytest.approx(1.0) and s.quality == 50
    assert caps.parse_status({}).facing is CameraFacing.BACK


def test_exposure_range_from_avail() -> None:
    c = caps.parse_capabilities({"avail": {"torch": ["off"], "exposure": ["-20", "0", "20"]}})
    assert c is not None
    assert (c.exposure_min, c.exposure_max) == (-20, 20)
    assert c.has_exposure


def test_sensors() -> None:
    info = caps.parse_sensors(
        {
            "battery_level": {"data": [[1, [50.0]], [2, [78.0]]]},
            "battery_charging": {"data": [[2, [0.0]]]},
        }
    )
    assert info.battery_percent == pytest.approx(78.0)
    assert info.charging is False


def test_empty_sensors_like_real_phone() -> None:
    info = caps.parse_sensors({})
    assert info.battery_percent is None and info.charging is None


@pytest.mark.parametrize(("percent", "ratio"), [(0, 1.0), (50, 5.5), (100, 10.0), (150, 10.0)])
def test_zoom_ratio_mapping(percent: int, ratio: float) -> None:
    # /ptz?zoom=50 gave curvals.zoom "550" (5.5×) on the real phone
    c = CameraCapabilities(zoom_max_ratio=10.0)
    assert c.zoom_ratio(percent) == pytest.approx(ratio)


def test_zoom_percent_round_trip() -> None:
    c = CameraCapabilities(zoom_max_ratio=10.0)
    assert c.zoom_percent(5.5) == 50
    assert c.zoom_percent(1.0) == 0
    assert c.zoom_percent(20.0) == 100
    assert CameraCapabilities().zoom_percent(3.0) == 0  # no zoom support
