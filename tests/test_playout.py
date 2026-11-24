"""PlayoutBuffer: even display from bursty arrival, adaptivity, resets, low-latency mode."""

from __future__ import annotations

import itertools
import random
import statistics

import numpy as np
import pytest

from camdesk.core.frames import YUV420P, VideoFrame
from camdesk.core.playout import MAX_DELAY_S, PlayoutBuffer

FRAME_S = 1 / 30
_PLANES = (np.zeros((4, 4), np.uint8), np.zeros((2, 2), np.uint8), np.zeros((2, 2), np.uint8))


def frame(pts: float | None, arrived: float) -> VideoFrame:
    return VideoFrame(
        width=4, height=4, format=YUV420P, planes=_PLANES, pts_s=pts, received_at=arrived
    )


def simulate(buf: PlayoutBuffer, arrivals: list[tuple[float, float]], refresh_s: float = 1 / 60):
    """Feed (pts, arrival) and poll take() at every display refresh. Returns display times."""
    shown: list[tuple[float, float]] = []  # (display time, pts)
    events = sorted(arrivals, key=lambda a: a[1])
    t, i, end = 0.0, 0, events[-1][1] + 0.5
    while t < end:
        while i < len(events) and events[i][1] <= t:
            buf.put(frame(*events[i]))
            i += 1
        f = buf.take(now=t)
        if f is not None:
            shown.append((t, f.pts_s))
        t += refresh_s
    return shown


def bursty_wifi(n: int = 300, seed: int = 1) -> list[tuple[float, float]]:
    """Like the measured phone: perfect 33.3 ms capture, Wi-Fi adds 0–90 ms bursts."""
    rng = random.Random(seed)
    out, net = [], 0.010
    for k in range(n):
        if rng.random() < 0.08:
            net = rng.uniform(0.04, 0.09)  # a burst starts
        net = max(0.005, net * 0.8)  # and drains
        out.append((k * FRAME_S, 1000.0 + k * FRAME_S + net + rng.uniform(0, 0.004)))
    return out


def gaps_ms(shown: list[tuple[float, float]]) -> list[float]:
    return [(b[0] - a[0]) * 1000 for a, b in itertools.pairwise(shown)]


def test_smooth_mode_evens_out_bursty_arrival() -> None:
    arrivals = bursty_wifi()
    raw = [(b[1] - a[1]) * 1000 for a, b in itertools.pairwise(arrivals)]
    shown = simulate(PlayoutBuffer(smooth=True, clock=lambda: 0.0), arrivals)
    smooth = gaps_ms(shown[30:])  # after the first second of learning
    assert statistics.pstdev(raw) > 8  # the input really is bursty
    assert sum(g > 50 for g in smooth) == 0  # no visible stutter left
    assert statistics.pstdev(smooth) < 9  # only 33/50 ms refresh-grid alternation remains
    assert [p for _, p in shown] == sorted(p for _, p in shown)  # never goes back in time


def test_low_latency_mode_shows_frames_at_arrival() -> None:
    arrivals = bursty_wifi()
    buf = PlayoutBuffer(smooth=False)
    shown = simulate(buf, arrivals)
    first_arrival = arrivals[0][1]
    assert shown[0][0] - first_arrival < 1 / 60 + 1e-9  # shown at the next refresh
    assert buf.delay_s == 0.0


def test_delay_adapts_and_is_capped() -> None:
    calm = [(k * FRAME_S, 1000 + k * FRAME_S + 0.010) for k in range(100)]
    buf = PlayoutBuffer(clock=lambda: 0.0)
    for pts, arr in calm:
        buf.put(frame(pts, arr))
    assert buf.delay_s < 0.015  # steady Wi-Fi: almost no added delay
    stormy = [
        (k * FRAME_S, 1000 + k * FRAME_S + (0.5 if k % 3 == 0 else 0.01)) for k in range(100, 200)
    ]
    for pts, arr in stormy:
        buf.put(frame(pts, arr))
    assert buf.delay_s == pytest.approx(MAX_DELAY_S)  # never more than the cap


def test_timestamp_jump_resets_schedule() -> None:
    buf = PlayoutBuffer(clock=lambda: 0.0)
    for k in range(50):
        buf.put(frame(k * FRAME_S, 1000 + k * FRAME_S + 0.05))
    buf.take(now=2000)  # drain
    buf.put(frame(0.0, 1100.0))  # reconnect: phone clock starts over
    assert buf.take(now=1100.02) is not None  # due within one refresh, not seconds later


def test_frames_without_pts_show_immediately() -> None:
    buf = PlayoutBuffer()
    buf.put(frame(None, 5.0))
    assert buf.take(now=5.0) is not None


def test_wake_up_contract() -> None:
    """The first frame after the queue empties must ask the UI to wake up (no stall)."""
    buf = PlayoutBuffer(clock=lambda: 0.0)
    assert buf.put(frame(0.0, 100.0)) is True
    assert buf.put(frame(FRAME_S, 100.0 + FRAME_S)) is False  # UI is already looping
    buf.take(now=1e9)  # everything due: queue now empty
    assert not buf.pending
    assert buf.put(frame(2 * FRAME_S, 100.0 + 2 * FRAME_S)) is True


def test_queue_is_bounded_and_peek_is_latest() -> None:
    buf = PlayoutBuffer(clock=lambda: 0.0)
    for k in range(100):  # nobody consuming
        buf.put(frame(k * FRAME_S, 1000 + k * FRAME_S))
    assert buf.dropped >= 70
    latest = buf.peek()
    assert latest is not None and latest.pts_s == pytest.approx(99 * FRAME_S)


def test_switching_modes_live() -> None:
    buf = PlayoutBuffer(smooth=True, clock=lambda: 0.0)
    for k in range(20):
        buf.put(frame(k * FRAME_S, 1000 + k * FRAME_S + 0.05))
    buf.set_smooth(False)
    assert buf.take(now=1000.1) is not None  # queued frames are due at their arrival time
