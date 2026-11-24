"""StreamService — runs a VideoSource on its own thread, with reconnect and stats.

    StreamService(buffer, [rtsp_factory, mjpeg_factory]).start()

- Frames go into the LatestFrameBuffer; `frame_ready` fires only when the UI has taken the
  previous frame (no event flooding, latency can't build up).
- Raw packets go to packet sinks (the recorder) on the stream thread — keep sinks fast.
- On failure: RECONNECTING with backoff 0.5 s → 1 → 2 → 4 → 8 → 10 s. After
  `max_failures` attempts in a row without a frame: FAILED, until retry() is called.
- Every second failed attempt switches to the next source (RTSP → MJPEG fallback).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QObject, Signal

from camdesk.core.errors import StreamError
from camdesk.core.frames import LatestFrameBuffer, VideoFrame
from camdesk.core.models import ConnectionState, StreamInfo
from camdesk.stream.source import SourceFactory, VideoSource
from camdesk.utils.timing import RateCounter

log = logging.getLogger(__name__)

DEFAULT_BACKOFF_S = (0.5, 1.0, 2.0, 4.0, 8.0, 10.0)
STATS_INTERVAL_S = 1.0
PacketSink = Callable[[Any], None]


class StreamService(QObject):
    state_changed = Signal(object, str)  # ConnectionState, message
    stream_info_changed = Signal(object)  # StreamInfo
    frame_ready = Signal()

    def __init__(
        self,
        buffer: LatestFrameBuffer,
        factories: Sequence[SourceFactory],
        *,
        max_failures: int = 5,
        backoff_s: Sequence[float] = DEFAULT_BACKOFF_S,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not factories:
            raise ValueError("At least one source factory is required")
        self.buffer = buffer
        self._factories = list(factories)
        self._max_failures = max_failures
        self._backoff = tuple(backoff_s)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._sinks: list[PacketSink] = []
        self._sinks_lock = threading.Lock()
        self._state = ConnectionState.IDLE
        self._source: VideoSource | None = None

    # -- public API (any thread) -----------------------------------------

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, name="StreamService", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        """Stop the stream thread.

        timeout_s > 0 waits for it (app exit, tests). timeout_s = 0 returns at once — use this
        on the UI thread; the thread notices the stop flag and ends by itself within the
        source's read timeout.
        """
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            if timeout_s > 0:
                self._thread.join(timeout_s)
                if self._thread.is_alive():
                    log.warning("Stream thread did not stop within %.1f s", timeout_s)
            self._thread = None
        self.buffer.clear()
        self._set_state(ConnectionState.IDLE, "")

    def retry(self) -> None:
        """Try again now (skips the backoff wait, leaves FAILED)."""
        self._wake.set()

    def add_packet_sink(self, sink: PacketSink) -> None:
        with self._sinks_lock:
            self._sinks.append(sink)

    def remove_packet_sink(self, sink: PacketSink) -> None:
        with self._sinks_lock:
            if sink in self._sinks:
                self._sinks.remove(sink)

    @property
    def source(self) -> VideoSource | None:
        """The source currently open (stream thread owns it — read only)."""
        return self._source

    # -- stream thread -----------------------------------------------------

    def _run(self) -> None:
        failures = 0
        index = 0
        ever_connected = False
        while not self._stop.is_set():
            source = self._factories[index]()
            self._set_state(
                ConnectionState.RECONNECTING
                if ever_connected or failures
                else ConnectionState.CONNECTING,
                f"Reconnecting… (attempt {failures + 1})" if failures else "Connecting…",
            )
            got_frame = False
            message = ""
            try:
                source.open()
                self._source = source
                got_frame = self._pump(source)
                if not self._stop.is_set():
                    message = "The video stream ended"
            except StreamError as exc:
                message = str(exc)
            except Exception:
                log.exception("Unexpected error in video stream")
                message = "The video stream failed"
            finally:
                self._source = None
                source.close()

            if self._stop.is_set():
                break
            log.warning("Stream (%s) stopped: %s", source.transport, message)
            ever_connected = ever_connected or got_frame
            failures = 0 if got_frame else failures + 1
            if len(self._factories) > 1 and failures and failures % 2 == 0:
                index = (index + 1) % len(self._factories)
                log.info("Switching video source to %s", index)

            if failures >= self._max_failures:
                self._set_state(ConnectionState.FAILED, message)
                self._wake.wait()  # until retry() or stop()
                self._wake.clear()
                failures = 0
                index = 0
                continue
            delay = self._backoff[min(max(failures - 1, 0), len(self._backoff) - 1)]
            self._set_state(ConnectionState.RECONNECTING, message)
            if self._wake.wait(delay):
                self._wake.clear()

    def _pump(self, source: VideoSource) -> bool:
        """Read until the source ends. Returns True if at least one frame arrived."""
        fps = RateCounter()
        bitrate = RateCounter()
        got_frame = False
        last_stats = 0.0
        for item in source.read():
            if self._stop.is_set():
                break
            if isinstance(item, VideoFrame):
                fps.add()
                if not got_frame:
                    got_frame = True
                    self._set_state(ConnectionState.CONNECTED, "")
                if self.buffer.put(item):
                    self.frame_ready.emit()
                now = time.perf_counter()
                if now - last_stats >= STATS_INTERVAL_S:
                    last_stats = now
                    self.stream_info_changed.emit(
                        StreamInfo(
                            width=item.width,
                            height=item.height,
                            fps=round(fps.rate, 1),
                            bitrate_kbps=round(bitrate.kbps) if bitrate.kbps else None,
                            decoder=source.decoder,
                            transport=source.transport,
                        )
                    )
            else:
                bitrate.add(getattr(item, "size", 0))
                self._feed_sinks(item)
        return got_frame

    def _feed_sinks(self, packet: Any) -> None:
        with self._sinks_lock:
            sinks = list(self._sinks)
        for sink in sinks:
            try:
                sink(packet)
            except Exception:
                log.exception("Packet sink failed; removing it")
                self.remove_packet_sink(sink)

    def _set_state(self, state: ConnectionState, message: str) -> None:
        if state is self._state and state is not ConnectionState.RECONNECTING:
            return
        self._state = state
        self.state_changed.emit(state, message)
