"""MKV recorder: remuxes the phone's H.264 + AAC packets. No decoding, no re-encoding.

    recorder.start(folder, segment_s)      # UI thread
    stream_service.add_packet_sink(recorder.push)   # stream thread calls push(packet)
    recorder.stop()

- push() copies each packet (bytes + timing) into a queue: the original packet object is
  still being decoded on the stream thread, so we never touch it after push returns.
- The writer thread starts every file on a video keyframe and rebases timestamps to 0
  using one shared time origin for video and audio, so A/V stay in sync.
- Splits into <name>_part2.mkv … at the first keyframe after `segment_s`, and also when the
  stream itself changes (a reconnect gives new stream parameters).
- Stops on its own when the disk gets almost full.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
from PySide6.QtCore import QObject, Signal

from camdesk.capture import storage

log = logging.getLogger(__name__)

QUEUE_LIMIT = 2000  # ~1 min of packets; if the disk can't keep up we drop, not grow forever
DISK_CHECK_S = 10.0
STOPPED_DISK_FULL = "Recording stopped: the disk is almost full"
WRITE_FAILED = "Recording stopped: couldn't write the file"


@dataclass(slots=True)
class _Copy:
    kind: str  # "video" | "audio"
    data: bytes
    pts: int | None
    dts: int | None
    time_base: Fraction
    keyframe: bool
    source: Any  # the input container: a new one means the stream was reopened
    template: Any  # the input stream (codec parameters for the output stream)


class _Stop:
    pass


class Recorder(QObject):
    started = Signal(str)  # first file path
    part_started = Signal(int, str)  # part number, path
    stopped = Signal(str)  # reason ("" = stopped by the user)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: queue.Queue[_Copy | _Stop] = queue.Queue(QUEUE_LIMIT)
        self._thread: threading.Thread | None = None
        self._active = threading.Event()
        self.dropped = 0

    @property
    def active(self) -> bool:
        return self._active.is_set()

    @property
    def busy(self) -> bool:
        """True while recording or still finishing the last file."""
        return self._thread is not None and self._thread.is_alive()

    # -- UI thread -------------------------------------------------------------

    def start(self, folder: Path, segment_s: float) -> Path:
        if self.busy:
            raise RuntimeError("Already recording or still finishing the last file")
        base = storage.recording_base(folder)
        self._queue = queue.Queue(QUEUE_LIMIT)
        self.dropped = 0
        self._active.set()
        self._thread = threading.Thread(
            target=self._run, args=(base, segment_s), name="Recorder", daemon=True
        )
        self._thread.start()
        return storage.part_path(base, 1)

    def stop(self, timeout_s: float = 5.0) -> None:
        """Finish the current file.

        timeout_s > 0 waits for the file to be complete (app exit, tests). timeout_s = 0
        returns at once — use this on the UI thread; `stopped` fires when the file is done.
        """
        if not self.active:
            return
        self._active.clear()
        with contextlib.suppress(queue.Full):
            self._queue.put(_Stop(), timeout=1.0)
        if self._thread is not None and timeout_s > 0:
            self._thread.join(timeout_s)

    # -- stream thread -----------------------------------------------------------

    def push(self, packet: Any) -> None:
        """Packet sink for StreamService. Cheap: copy and enqueue, never block."""
        if not self._active.is_set():
            return
        stream = packet.stream
        kind = stream.type
        if kind not in ("video", "audio"):
            return
        item = _Copy(
            kind=kind,
            data=bytes(packet),
            pts=packet.pts,
            dts=packet.dts,
            time_base=packet.time_base or stream.time_base,
            keyframe=bool(packet.is_keyframe),
            source=stream.container,
            template=stream,
        )
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    # -- writer thread -------------------------------------------------------------

    def _run(self, base: Path, segment_s: float) -> None:
        writer: _MkvWriter | None = None
        part = 0
        reason = ""
        last_disk_check = 0.0
        try:
            while True:
                item = self._queue.get()
                if isinstance(item, _Stop):
                    break
                now = time.monotonic()
                if now - last_disk_check > DISK_CHECK_S:
                    last_disk_check = now
                    free = storage.free_bytes(base.parent)
                    if free is not None and free < storage.LOW_DISK_STOP_BYTES:
                        reason = STOPPED_DISK_FULL
                        break
                needs_new = (
                    writer is None
                    or item.source is not writer.source
                    or (
                        item.kind == "video"
                        and item.keyframe
                        and writer.duration_s(item) >= segment_s
                    )
                )
                if needs_new:
                    if item.kind != "video" or not item.keyframe:
                        if writer is not None and item.source is writer.source:
                            writer.write(item)  # keep writing until the next keyframe
                        continue  # a file must start on a video keyframe
                    if writer is not None:
                        writer.close()
                    part += 1
                    path = storage.part_path(base, part)
                    writer = _MkvWriter(path, item)
                    log.info("Recording part %d: %s", part, path)
                    if part == 1:
                        self.started.emit(str(path))
                    self.part_started.emit(part, str(path))
                writer.write(item)  # type: ignore[union-attr]
        except (av.error.FFmpegError, OSError) as exc:
            log.exception("Recording failed")
            reason = f"{WRITE_FAILED} ({exc})"
        finally:
            if writer is not None:
                try:
                    writer.close()
                except (av.error.FFmpegError, OSError):
                    log.exception("Could not finish the recording file")
            self._active.clear()
            if self.dropped:
                log.warning("Recorder dropped %d packets (disk too slow?)", self.dropped)
            self.stopped.emit(reason)


class _MkvWriter:
    """One MKV file. Created on a video keyframe; that moment is time zero for all streams."""

    def __init__(self, path: Path, first: _Copy) -> None:
        self.path = path
        self.source = first.source
        self._container = av.open(str(path), "w", format="matroska")
        container_in = first.source
        self._out: dict[str, Any] = {}
        self._origin_s = (first.pts or 0) * first.time_base  # seconds, shared by both streams
        self._last_dts: dict[str, int] = {}
        for kind, streams in (
            ("video", container_in.streams.video),
            ("audio", container_in.streams.audio),
        ):
            if streams:
                self._out[kind] = self._container.add_stream_from_template(streams[0])

    def duration_s(self, item: _Copy) -> float:
        if item.pts is None:
            return 0.0
        return float(item.pts * item.time_base - self._origin_s)

    def write(self, item: _Copy) -> None:
        out = self._out.get(item.kind)
        if out is None or item.pts is None:
            return
        offset = round(self._origin_s / item.time_base)
        pts = item.pts - offset
        if pts < 0:
            return  # audio from just before the keyframe that started this file
        dts = (item.dts if item.dts is not None else item.pts) - offset
        dts = max(dts, self._last_dts.get(item.kind, -1) + 1) if item.kind == "audio" else dts
        packet = av.Packet(item.data)
        packet.pts, packet.dts = pts, min(dts, pts)
        packet.time_base = item.time_base
        packet.is_keyframe = item.keyframe
        packet.stream = out
        self._container.mux(packet)
        self._last_dts[item.kind] = packet.dts

    def close(self) -> None:
        self._container.close()
