from __future__ import annotations

import pytest

from camdesk.camera import capabilities as caps
from camdesk.core.models import CameraCapabilities, CameraFacing
from camdesk.dev.fake_camera import FakeCamera


def test_back_camera_from_fake(fake_camera: FakeCamera) -> None:
    data = fake_camera.status(show_avail=True)
    c = caps.parse_capabilities(data)
    assert c.has_torch and c.has_autofocus and c.has_front_camera and c.has_night_vision
    assert c.zoom_max_ratio == pytest.approx(10.0)
    assert "1920x1080" in c.video_sizes


def test_front_camera_has_no_torch_or_autofocus(fake_camera: FakeCamera) -> None:
    fake_camera.state["ffc"] = "on"
    data = fake_camera.status(show_avail=True)
    c = caps.parse_capabilities(data)
    s = caps.parse_status(data)
    assert s.facing is CameraFacing.FRONT
    assert not c.has_torch
    assert not c.has_autofocus


def test_status_values() -> None:
    data = {
        "curvals": {
            "torch": "on",
            "night_vision": "off",
            "zoom": "37",
            "quality": "70",
            "video_size": "1280x720",
            "ffc": "off",
        }
    }
    s = caps.parse_status(data)
    assert s.torch and not s.night_vision
    assert s.zoom_percent == 37
    assert s.quality == 70
    assert s.video_size == "1280x720"
    assert s.facing is CameraFacing.BACK


def test_missing_fields_use_safe_defaults() -> None:
    s = caps.parse_status({})
    c = caps.parse_capabilities({})
    assert s.zoom_percent == 0 and s.quality == 50
    assert c.has_torch  # unknown -> assume back camera behavior
    assert not c.has_zoom and not c.has_exposure and not c.has_front_camera


def test_garbage_values_do_not_crash() -> None:
    s = caps.parse_status({"curvals": {"zoom": "abc", "quality": None}})
    assert s.zoom_percent == 0 and s.quality == 50


def test_exposure_range_from_avail() -> None:
    c = caps.parse_capabilities({"avail": {"exposure": ["-20", "0", "20"]}})
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
    assert caps.parse_sensors({}).battery_percent is None


@pytest.mark.parametrize(("percent", "ratio"), [(0, 1.0), (50, 5.5), (100, 10.0), (150, 10.0)])
def test_zoom_ratio_mapping(percent: int, ratio: float) -> None:
    c = CameraCapabilities(zoom_max_ratio=10.0)
    assert c.zoom_ratio(percent) == pytest.approx(ratio)


def test_zoom_percent_round_trip() -> None:
    c = CameraCapabilities(zoom_max_ratio=10.0)
    assert c.zoom_percent(2.5) == 17
    assert c.zoom_percent(1.0) == 0
    assert c.zoom_percent(20.0) == 100
    assert CameraCapabilities().zoom_percent(3.0) == 0  # no zoom support
