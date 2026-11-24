"""PlayoutBuffer — smooth playback by showing frames on the phone's clock.

Measured on the real phone: the camera captures every 33.5 ms with zero variation, but Wi-Fi
delivers frames in bursts (±15 ms, up to ~100 ms late). Showing each frame the instant it
arrives copies those bursts to the screen. This buffer instead schedules each frame at

    phone capture time  →  local time  +  a small adaptive delay

and the video widget, repainting at every display refresh, shows whichever frame is due.

- Phone→local clock offset = the *least* delayed recent frame (sliding window), so slow
  clock drift between phone and PC is followed automatically.
- Adaptive delay = 95th percentile of recent lateness (+ a small margin), capped. It rises at
  once when Wi-Fi gets worse and decays slowly when it calms down.
- A jump in phone timestamps (reconnect, encoder restart) resets the schedule.
- smooth=False behaves exactly like LatestFrameBuffer (lowest latency, no scheduling).

Same API as LatestFrameBuffer (put/take/peek/has_new/clear/dropped/delivered), so everything
else works with either.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from camdesk.core.frames import VideoFrame

WINDOW = 150  # frames used for offset and lateness (~5 s at 30 FPS)
MARGIN_S = 0.008  # covers display-refresh granularity
MAX_DELAY_S = 0.150  # never add more than this (delay vs. smoothness trade-off)
DECAY = 0.02  # how fast the delay shrinks per frame when Wi-Fi calms down
MAX_QUEUE = 30  # ~1 s; beyond that the oldest frames are dropped
RESET_JUMP_S = 2.0  # phone timestamps jumping this much = new stream


class PlayoutBuffer:
    def __init__(
        self,
        smooth: bool = True,
        clock: Callable[[], float] = time.perf_counter,
        max_delay_s: float = MAX_DELAY_S,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._max_delay = max_delay_s
        self._smooth = smooth
        self._queue: deque[tuple[float, VideoFrame]] = deque()
        self._latest: VideoFrame | None = None
        self._idle = True  # consumer has nothing pending: the next put should notify
        self._refs: deque[float] = deque(maxlen=WINDOW)  # arrival - pts per frame
        self._last_pts: float | None = None
        self.delay_s = 0.0  # current adaptive delay (shown in the debug overlay)
        self.dropped = 0
        self.delivered = 0

    # -- settings ------------------------------------------------------------------

    @property
    def smooth(self) -> bool:
        return self._smooth

    def set_smooth(self, smooth: bool) -> None:
        with self._lock:
            self._smooth = smooth
            self._reset_schedule()

    # -- producer (stream thread) -----------------------------------------------------

    def put(self, frame: VideoFrame) -> bool:
        """Queue a frame. Returns True when the consumer was idle and should be woken."""
        with self._lock:
            self._latest = frame
            if not self._smooth:
                if self._queue:
                    self.dropped += len(self._queue)
                self._queue.clear()
                self._queue.append((frame.received_at, frame))
            else:
                # Schedule first: _schedule() may reset and *replace* self._queue, and
                # `self._queue.append(...)` would otherwise bind the old, discarded deque.
                due = self._schedule(frame)
                self._queue.append((due, frame))
                while len(self._queue) > MAX_QUEUE:
                    self._queue.popleft()
                    self.dropped += 1
            notify, self._idle = self._idle, False
            return notify

    def _schedule(self, frame: VideoFrame) -> float:
        pts = frame.pts_s
        if pts is None:
            return frame.received_at  # no phone clock (e.g. some MJPEG): show at once
        last = self._last_pts
        if last is not None and (pts < last or pts - last > RESET_JUMP_S):
            self._reset_schedule()
        self._last_pts = pts
        ref = frame.received_at - pts
        self._refs.append(ref)
        offset = min(self._refs)
        lateness = sorted(r - offset for r in self._refs)
        p95 = lateness[int(len(lateness) * 0.95)] if len(lateness) >= 10 else lateness[-1]
        target = min(self._max_delay, p95 + MARGIN_S)
        # Rise at once, fall slowly: a calm second shouldn't undo protection from bursts.
        self.delay_s = (
            target if target > self.delay_s else self.delay_s + DECAY * (target - self.delay_s)
        )
        return pts + offset + self.delay_s

    def _reset_schedule(self) -> None:
        self._refs.clear()
        self._last_pts = None
        self.delay_s = 0.0
        # Whatever is still queued is shown right away (its old schedule no longer applies).
        self._queue = deque((f.received_at, f) for _, f in self._queue)

    # -- consumer (UI thread, once per display refresh) ---------------------------------

    def take(self, now: float | None = None) -> VideoFrame | None:
        """The newest frame that is due now (older due frames are skipped), or None."""
        with self._lock:
            if not self._queue:
                self._idle = True
                return None
            now = self._clock() if now is None else now
            picked: VideoFrame | None = None
            while self._queue and self._queue[0][0] <= now:
                if picked is not None:
                    self.dropped += 1
                picked = self._queue.popleft()[1]
            if picked is not None:
                self.delivered += 1
            # Empty queue = the UI stops its refresh loop, so the next put must wake it.
            self._idle = not self._queue
            return picked

    @property
    def pending(self) -> bool:
        """Frames are waiting for their time: the UI should paint again when one is due."""
        with self._lock:
            return bool(self._queue)

    @property
    def next_due(self) -> float | None:
        """When the next queued frame should be shown (perf_counter time), or None."""
        with self._lock:
            return self._queue[0][0] if self._queue else None

    @property
    def has_new(self) -> bool:
        return self.pending

    def peek(self) -> VideoFrame | None:
        """The most recently received frame (for snapshots)."""
        with self._lock:
            return self._latest

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._latest = None
            self._idle = True
            self._reset_schedule()
