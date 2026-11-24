from __future__ import annotations

import pytest

from camdesk.ui import win_frame as wf

W, H, B = 1000, 600, 6


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (0, 0, wf.HTTOPLEFT),
        (W - 1, 0, wf.HTTOPRIGHT),
        (0, H - 1, wf.HTBOTTOMLEFT),
        (W - 1, H - 1, wf.HTBOTTOMRIGHT),
        (0, 300, wf.HTLEFT),
        (W - 1, 300, wf.HTRIGHT),
        (500, 0, wf.HTTOP),
        (500, H - 1, wf.HTBOTTOM),
        (500, 300, wf.HTCLIENT),
    ],
)
def test_resize_edges(x: int, y: int, expected: int) -> None:
    assert wf.hit_test(x, y, W, H, B, resizable=True, in_caption=False) == expected


def test_caption_and_edges_priority() -> None:
    # Resize edge wins over the caption at the very top (like native windows)…
    assert wf.hit_test(500, 2, W, H, B, resizable=True, in_caption=True) == wf.HTTOP
    # …but inside the bar it's the caption.
    assert wf.hit_test(500, 20, W, H, B, resizable=True, in_caption=True) == wf.HTCAPTION


def test_maximized_has_no_resize_edges() -> None:
    assert wf.hit_test(0, 0, W, H, B, resizable=False, in_caption=True) == wf.HTCAPTION
    assert wf.hit_test(0, 300, W, H, B, resizable=False, in_caption=False) == wf.HTCLIENT
