from __future__ import annotations

import pytest

from camdesk.camera import endpoints as ep
from camdesk.core.geometry import focus_point, rotate_orientation, toggle_flip_mode


@pytest.mark.parametrize(
    ("start", "steps", "expected"),
    [
        ("landscape", 1, "portrait"),
        ("portrait", 1, "upsidedown"),
        ("upsidedown_portrait", 1, "landscape"),  # wraps
        ("landscape", -1, "upsidedown_portrait"),
        ("unknown", 1, "portrait"),  # unknown value starts from landscape
    ],
)
def test_rotate(start: str, steps: int, expected: str) -> None:
    assert rotate_orientation(start, steps) == expected


def test_rotate_only_through_available() -> None:
    assert rotate_orientation("landscape", 1, ("landscape", "upsidedown")) == "upsidedown"


@pytest.mark.parametrize(
    ("current", "part", "expected"),
    [
        ("none", "mirror", "mirror"),
        ("mirror", "mirror", "none"),
        ("mirror", "flip", "mirror,flip"),
        ("mirror,flip", "mirror", "flip"),
        ("", "flip", "flip"),
    ],
)
def test_toggle_flip_mode(current: str, part: str, expected: str) -> None:
    assert toggle_flip_mode(current, part) == expected


@pytest.mark.parametrize(
    ("nx", "ny", "orientation", "flip", "expected"),
    [
        (0.5, 0.5, "landscape", "none", (0, 0)),  # center
        (0.0, 0.0, "landscape", "none", (-1000, -1000)),  # top-left
        (1.0, 1.0, "landscape", "none", (1000, 1000)),
        (0.25, 0.5, "landscape", "mirror", (500, 0)),  # mirrored: left on screen = right on sensor
        (0.25, 0.25, "upsidedown", "none", (500, 500)),
        (0.5, 0.25, "landscape", "flip", (0, 500)),
    ],
)
def test_focus_point(nx: float, ny: float, orientation: str, flip: str, expected) -> None:
    assert focus_point(nx, ny, orientation, flip) == expected


def test_focus_region_command_uses_comma_and_clamps() -> None:
    cmd = ep.focus_region(200, -300)
    assert cmd.path == "/settings/focus_region" and cmd.params == (("set", "200,-300"),)
    assert ep.focus_region(5000, -5000).params == (("set", "1000,-1000"),)
    assert ep.mirror_flip("mirror,flip").params == (("set", "mirror,flip"),)
