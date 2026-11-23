"""Rolling-window counters for FPS and bitrate."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class RateCounter:
    """Events (and optional byte totals) per second over a rolling time window."""

    def __init__(self, window_s: float = 2.0, clock: Callable[[], float] = time.perf_counter):
        self.window_s = window_s
        self._clock = clock
        self._events: deque[tuple[float, int]] = deque()
        self._bytes = 0

    def add(self, nbytes: int = 0) -> None:
        now = self._clock()
        self._events.append((now, nbytes))
        self._bytes += nbytes
        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._events and self._events[0][0] < cutoff:
            _, nbytes = self._events.popleft()
            self._bytes -= nbytes

    def _span(self) -> float:
        self._trim(self._clock())
        if len(self._events) < 2:
            return 0.0
        return self._events[-1][0] - self._events[0][0]

    @property
    def rate(self) -> float:
        """Events per second."""
        span = self._span()
        return (len(self._events) - 1) / span if span > 0 else 0.0

    @property
    def kbps(self) -> float:
        """Kilobits per second of the bytes passed to add()."""
        span = self._span()
        if span <= 0:
            return 0.0
        first_bytes = self._events[0][1]  # bytes of the first event arrived before the span
        return (self._bytes - first_bytes) * 8 / span / 1000

    def reset(self) -> None:
        self._events.clear()
        self._bytes = 0
