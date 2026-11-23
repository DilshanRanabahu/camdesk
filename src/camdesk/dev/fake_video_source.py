"""A synthetic video source: a moving test pattern, no network or files needed.

Used by tests and by `--fake` mode. It can also simulate failures:
- `fail_opens=N`        → the first N open() calls fail (like an unreachable phone)
- `frames_per_open=N`   → each connection breaks after N frames (like Wi-Fi dropping)
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Iterator

import numpy as np

from camdesk.core.errors import StreamError
from camdesk.core.frames import YUV420P, VideoFrame
from camdesk.stream.source import SourceItem, VideoSource


class FakeVideoPlan:
    """Shared state across reconnects (each reconnect creates a new FakeVideoSource)."""

    def __init__(
        self,
        width: int = 640,
        height: int = 360,
        fps: float = 30.0,
        fail_opens: int = 0,
        frames_per_open: int | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.fail_opens = fail_opens
        self.frames_per_open = frames_per_open
        self.opens = 0
        self._lock = threading.Lock()

    def factory(self) -> FakeVideoSource:
        return FakeVideoSource(self)

    def next_open_fails(self) -> bool:
        with self._lock:
            self.opens += 1
            return self.opens <= self.fail_opens


class FakeVideoSource(VideoSource):
    transport = "fake"

    def __init__(self, plan: FakeVideoPlan) -> None:
        self.plan = plan
        self._open = False
        self._closed = threading.Event()

    @property
    def decoder(self) -> str:
        return "Test pattern"

    def open(self) -> None:
        if self.plan.next_open_fails():
            raise StreamError("Can't reach the phone")
        self._open = True

    def read(self) -> Iterator[SourceItem]:
        if not self._open:
            raise StreamError("Source is not open")
        w, h = self.plan.width, self.plan.height
        interval = 1.0 / self.plan.fps
        y_base = np.tile(np.linspace(16, 235, w, dtype=np.uint8), (h, 1))
        u = np.full((h // 2, w // 2), 128, np.uint8)
        v = np.full((h // 2, w // 2), 128, np.uint8)
        start = time.perf_counter()
        limit = self.plan.frames_per_open
        for n in itertools.count():
            if self._closed.is_set():
                return
            if limit is not None and n >= limit:
                raise StreamError("The connection to the phone was lost")
            y = y_base.copy()
            x = (n * 8) % w
            y[:, x : x + 24] = 235  # moving white bar shows smoothness at a glance
            yield VideoFrame(
                width=w,
                height=h,
                format=YUV420P,
                planes=(y, u, v),
                pts_s=n * interval,
                received_at=time.perf_counter(),
            )
            # Pace like a real camera (sleeping is fine: this is the stream thread).
            delay = start + (n + 1) * interval - time.perf_counter()
            if delay > 0:
                self._closed.wait(delay)

    def close(self) -> None:
        self._closed.set()
        self._open = False
