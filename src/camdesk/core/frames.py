"""Decoded video frames and the latest-frame buffer shared by the stream thread and the UI.

Lives in core/ (not stream/) because the UI's video widget reads frames, and the UI may
only import core/ (AGENTS.md rule 2). Depends only on numpy — no FFmpeg, no Qt.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Pixel formats the video widget can draw directly with a shader.
NV12 = "nv12"  # Y plane + interleaved UV plane (GPU decoders)
YUV420P = "yuv420p"  # Y, U, V planes (software decoder)
SUPPORTED_FORMATS = (NV12, YUV420P)


@dataclass(frozen=True, slots=True)
class VideoFrame:
    """One decoded frame.

    `planes` are 2-D uint8 arrays shaped (rows, line_size_in_bytes). Rows may be padded:
    only the first `row_bytes(i)` bytes of each row are picture data. The arrays may be
    zero-copy views into decoder memory; `keepalive` holds that memory alive.
    """

    width: int
    height: int
    format: str
    planes: tuple[np.ndarray, ...]
    pts_s: float | None = None  # presentation time in seconds (stream clock)
    received_at: float = 0.0  # time.perf_counter() when the frame was decoded
    full_range: bool = False  # True: 0–255 (JPEG); False: 16–235 (TV/video)
    bt709: bool = False  # color matrix: BT.709 (HD) if True, else BT.601
    keepalive: Any = field(default=None, repr=False, compare=False)

    def row_bytes(self, plane: int) -> int:
        if self.format == NV12:
            return self.width  # Y: 1 byte/px; UV: (width/2) pairs × 2 bytes
        if self.format == YUV420P:
            return self.width if plane == 0 else (self.width + 1) // 2
        raise ValueError(f"Unsupported pixel format: {self.format}")

    def plane_height(self, plane: int) -> int:
        return self.height if plane == 0 else (self.height + 1) // 2

    def plane_view(self, plane: int) -> np.ndarray:
        """Picture data without row padding (a view, no copy)."""
        return self.planes[plane][: self.plane_height(plane), : self.row_bytes(plane)]


class LatestFrameBuffer:
    """Holds only the newest frame. Producers overwrite; the consumer takes.

    Old frames are dropped instead of queued, so display latency can never build up.
    `put()` returns True only when the consumer had already taken the previous frame —
    the producer uses that to send one "frame ready" signal instead of flooding the UI.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: VideoFrame | None = None
        self._taken = True
        self.dropped = 0
        self.delivered = 0

    def put(self, frame: VideoFrame) -> bool:
        with self._lock:
            if not self._taken:
                self.dropped += 1
            notify = self._taken
            self._frame = frame
            self._taken = False
            return notify

    def take(self) -> VideoFrame | None:
        """Return the newest frame not yet taken, or None."""
        with self._lock:
            if self._taken:
                return None
            self._taken = True
            self.delivered += 1
            return self._frame

    @property
    def has_new(self) -> bool:
        """A frame is waiting that the consumer hasn't taken yet."""
        with self._lock:
            return not self._taken

    def peek(self) -> VideoFrame | None:
        """The most recent frame, taken or not (e.g. for snapshots or redraws)."""
        with self._lock:
            return self._frame

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._taken = True
