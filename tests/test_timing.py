from __future__ import annotations

import pytest

from camdesk.utils.timing import RateCounter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_fps_and_bitrate() -> None:
    clock = FakeClock()
    counter = RateCounter(window_s=2.0, clock=clock)
    for _ in range(31):  # 31 events over 1 s = 30 intervals
        counter.add(1000)
        clock.now += 1 / 30
    clock.now -= 1 / 30
    assert counter.rate == pytest.approx(30.0)
    assert counter.kbps == pytest.approx(30 * 1000 * 8 / 1000)


def test_old_events_drop_out_of_window() -> None:
    clock = FakeClock()
    counter = RateCounter(window_s=1.0, clock=clock)
    counter.add()
    counter.add()
    clock.now += 5
    assert counter.rate == 0.0
    assert counter.kbps == 0.0


def test_empty_and_reset() -> None:
    counter = RateCounter()
    assert counter.rate == 0.0
    counter.add(10)
    counter.reset()
    assert counter.kbps == 0.0
