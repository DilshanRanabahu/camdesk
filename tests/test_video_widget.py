"""Render real frames with OpenGL and read the pixels back to check the YUV → RGB shader."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from camdesk.core.frames import NV12, YUV420P, LatestFrameBuffer, VideoFrame
from camdesk.ui.video.video_widget import VideoWidget, ViewMode

W, H = 64, 36


def solid(
    fmt: str, y: int, u: int, v: int, *, full_range: bool = False, pad: int = 0
) -> VideoFrame:
    """A single-color frame, with optional row padding to test GL_UNPACK_ROW_LENGTH."""
    ys = np.full((H, W + pad), y, np.uint8)
    if fmt == NV12:
        uv = np.zeros((H // 2, W + pad), np.uint8)
        uv[:, 0:W:2], uv[:, 1:W:2] = u, v
        planes: tuple[np.ndarray, ...] = (ys, uv)
    else:
        planes = (
            ys,
            np.full((H // 2, W // 2 + pad), u, np.uint8),
            np.full((H // 2, W // 2 + pad), v, np.uint8),
        )
    return VideoFrame(width=W, height=H, format=fmt, planes=planes, full_range=full_range)


@pytest.fixture
def widget(qapp: QApplication):
    w = VideoWidget(LatestFrameBuffer())
    w.resize(W * 4, H * 4)
    w.show()
    qapp.processEvents()
    if w.context() is None or not w.context().isValid():
        w.close()
        pytest.skip("No OpenGL context available")
    yield w
    w.close()


def render(widget: VideoWidget, frame: VideoFrame) -> tuple[int, int, int]:
    widget.buffer.put(frame)
    image = widget.grabFramebuffer()  # runs paintGL
    c = image.pixelColor(image.width() // 2, image.height() // 2)
    return c.red(), c.green(), c.blue()


def close(actual: tuple[int, int, int], expected: tuple[int, int, int], tol: int = 8) -> bool:
    return all(abs(a - e) <= tol for a, e in zip(actual, expected, strict=True))


# BT.601 reference colors: (Y, Cb, Cr) → RGB
LIMITED = [
    ((81, 90, 240), (255, 0, 0)),
    ((145, 54, 34), (0, 255, 0)),
    ((41, 240, 110), (0, 0, 255)),
    ((235, 128, 128), (255, 255, 255)),
    ((16, 128, 128), (0, 0, 0)),
]
FULL = [
    ((76, 85, 255), (255, 0, 0)),
    ((255, 128, 128), (255, 255, 255)),
    ((0, 128, 128), (0, 0, 0)),
]


@pytest.mark.parametrize("fmt", [NV12, YUV420P])
@pytest.mark.parametrize(("yuv", "rgb"), LIMITED)
def test_limited_range_colors(widget: VideoWidget, fmt: str, yuv, rgb) -> None:
    assert close(render(widget, solid(fmt, *yuv)), rgb)


@pytest.mark.parametrize(("yuv", "rgb"), FULL)
def test_full_range_colors(widget: VideoWidget, yuv, rgb) -> None:
    assert close(render(widget, solid(YUV420P, *yuv, full_range=True)), rgb)


@pytest.mark.parametrize("fmt", [NV12, YUV420P])
def test_row_padding_is_skipped(widget: VideoWidget, fmt: str) -> None:
    assert close(render(widget, solid(fmt, 81, 90, 240, pad=32)), (255, 0, 0))


def test_frame_size_change_reallocates(widget: VideoWidget) -> None:
    render(widget, solid(NV12, 81, 90, 240))
    big = VideoFrame(
        width=128,
        height=72,
        format=YUV420P,
        planes=(
            np.full((72, 128), 145, np.uint8),
            np.full((36, 64), 54, np.uint8),
            np.full((36, 64), 34, np.uint8),
        ),
    )
    assert close(render(widget, big), (0, 255, 0))


def test_letterbox_is_black_in_fit_mode(widget: VideoWidget) -> None:
    widget.resize(400, 400)  # square widget, 16:9 video -> bars top and bottom
    widget.buffer.put(solid(YUV420P, 235, 128, 128))
    image = widget.grabFramebuffer()
    top = image.pixelColor(image.width() // 2, 2)
    middle = image.pixelColor(image.width() // 2, image.height() // 2)
    assert (top.red(), top.green(), top.blue()) == (0, 0, 0)
    assert middle.red() > 240


@pytest.mark.parametrize(
    ("mode", "size", "expected"),
    [
        (ViewMode.FIT, (1600, 900), (1.0, 1.0)),
        (ViewMode.FIT, (900, 900), (1.0, 0.5625)),  # bars top/bottom
        (ViewMode.FILL, (900, 900), (16 / 9, 1.0)),  # cropped left/right
        (ViewMode.FIT, (1800, 900), (0.8889, 1.0)),  # bars left/right
    ],
)
def test_quad_scale(widget: VideoWidget, mode: ViewMode, size, expected) -> None:
    widget.set_view_mode(mode)
    widget.resize(*size)
    sx, sy = widget._quad_scale(1920, 1080)
    ratio = widget.devicePixelRatioF()
    if ratio == 1.0:
        assert (sx, sy) == pytest.approx(expected, abs=1e-3)
    else:  # scaling cancels out for FIT/FILL
        assert (sx, sy) == pytest.approx(expected, abs=1e-3)
