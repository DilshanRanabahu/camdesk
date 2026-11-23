from __future__ import annotations

import threading

import numpy as np
import pytest

from camdesk.core.frames import NV12, YUV420P, LatestFrameBuffer, VideoFrame


def make_frame(n: int = 0, fmt: str = YUV420P, w: int = 8, h: int = 4, pad: int = 0) -> VideoFrame:
    if fmt == NV12:
        planes = (np.zeros((h, w + pad), np.uint8), np.zeros((h // 2, w + pad), np.uint8))
    else:
        planes = (
            np.zeros((h, w + pad), np.uint8),
            np.zeros((h // 2, w // 2 + pad), np.uint8),
            np.zeros((h // 2, w // 2 + pad), np.uint8),
        )
    return VideoFrame(width=w, height=h, format=fmt, planes=planes, pts_s=float(n))


def test_put_take_and_notify() -> None:
    buf = LatestFrameBuffer()
    assert buf.take() is None
    assert buf.put(make_frame(1)) is True  # consumer idle -> notify
    assert buf.put(make_frame(2)) is False  # not taken yet -> no extra signal
    frame = buf.take()
    assert frame is not None and frame.pts_s == 2.0  # only the newest survives
    assert buf.dropped == 1 and buf.delivered == 1
    assert buf.take() is None  # nothing new
    assert buf.put(make_frame(3)) is True


def test_peek_and_clear() -> None:
    buf = LatestFrameBuffer()
    buf.put(make_frame(5))
    buf.take()
    peeked = buf.peek()
    assert peeked is not None and peeked.pts_s == 5.0
    buf.clear()
    assert buf.peek() is None and buf.take() is None


def test_threaded_producer_never_queues() -> None:
    buf = LatestFrameBuffer()

    def produce() -> None:
        for n in range(5000):
            buf.put(make_frame(n))

    t = threading.Thread(target=produce)
    t.start()
    taken = []
    while t.is_alive():
        frame = buf.take()
        if frame is not None:
            taken.append(frame.pts_s)
    t.join()
    last = buf.take()
    if last is not None:
        taken.append(last.pts_s)
    assert taken == sorted(taken)  # never goes back in time
    assert buf.peek() is not None and buf.peek().pts_s == 4999.0
    assert buf.dropped + buf.delivered >= len(taken)


@pytest.mark.parametrize(
    ("fmt", "rows", "heights"),
    [(NV12, [8, 8], [4, 2]), (YUV420P, [8, 4, 4], [4, 2, 2])],
)
def test_plane_geometry(fmt: str, rows: list[int], heights: list[int]) -> None:
    frame = make_frame(fmt=fmt, pad=16)
    for i, (row, height) in enumerate(zip(rows, heights, strict=True)):
        assert frame.row_bytes(i) == row
        assert frame.plane_view(i).shape == (height, row)  # padding removed
