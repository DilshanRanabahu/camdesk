"""Snapshots: the newest decoded frame → JPEG, encoded by FFmpeg on a worker thread.

The frame is the same one shown on screen, so it already has the phone's rotation/mirror.
"""

from __future__ import annotations

import logging
import threading
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.reformatter import ColorRange
from PySide6.QtCore import QObject, Signal

from camdesk.capture import storage
from camdesk.core.frames import NV12, YUV420P, VideoFrame

log = logging.getLogger(__name__)

JPEG_QUALITY = 2  # FFmpeg mjpeg qscale: 2 = very high quality, 31 = worst


def frame_to_av(frame: VideoFrame) -> av.VideoFrame:
    """Rebuild an av.VideoFrame (contiguous, no row padding) from our planes."""
    w, h = frame.width, frame.height
    y = np.ascontiguousarray(frame.plane_view(0))
    if frame.format == NV12:
        uv = np.ascontiguousarray(frame.plane_view(1))
        data = np.vstack([y, uv])  # (h * 3/2, w)
        out = av.VideoFrame.from_ndarray(data, format="nv12")
    elif frame.format == YUV420P:
        u = np.ascontiguousarray(frame.plane_view(1)).reshape(-1, w)
        v = np.ascontiguousarray(frame.plane_view(2)).reshape(-1, w)
        out = av.VideoFrame.from_ndarray(np.vstack([y, u, v]), format="yuv420p")
    else:
        raise ValueError(f"Unsupported pixel format: {frame.format}")
    if out.width != w or out.height != h:
        raise ValueError("Frame size mismatch")
    return out


def encode_jpeg(frame: VideoFrame) -> bytes:
    source = frame_to_av(frame)
    # JPEG wants full range: let swscale convert from the video (TV) range when needed.
    src_range = ColorRange.JPEG if frame.full_range else ColorRange.MPEG
    source = source.reformat(
        format="yuvj420p", src_color_range=src_range, dst_color_range=ColorRange.JPEG
    )
    codec = av.CodecContext.create("mjpeg", "w")
    codec.width, codec.height = frame.width, frame.height
    codec.pix_fmt = "yuvj420p"
    codec.time_base = Fraction(1, 30)
    codec.qmin = codec.qmax = JPEG_QUALITY
    packets = codec.encode(source) + codec.encode(None)
    return b"".join(bytes(p) for p in packets)


def save_snapshot(frame: VideoFrame, folder: Path) -> Path:
    path = storage.snapshot_path(folder)
    data = encode_jpeg(frame)
    tmp = path.with_suffix(".jpg.part")
    tmp.write_bytes(data)
    tmp.replace(path)  # never leave a half-written .jpg
    return path


class SnapshotService(QObject):
    saved = Signal(str)  # path
    failed = Signal(str)  # message

    def take(self, frame: VideoFrame, folder: Path) -> None:
        """Encode and save on a worker thread; result arrives via `saved` / `failed`."""

        def work() -> None:
            try:
                path = save_snapshot(frame, folder)
            except Exception as exc:  # disk full, permissions, odd frame…
                log.exception("Snapshot failed")
                self.failed.emit(str(exc))
                return
            log.info("Snapshot saved: %s", path)
            self.saved.emit(str(path))

        threading.Thread(target=work, name="Snapshot", daemon=True).start()
