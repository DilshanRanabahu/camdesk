"""CaptureManager — snapshots and recording, on behalf of AppController.

Kept separate so AppController stays small. AppController tells it which stream is live
(`attach_stream` / `detach_stream`); the UI calls `snapshot()` and `toggle_recording()`.
Recorder signals come from the recorder thread and are connected to this object's methods,
so Qt queues them onto the UI thread.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Slot

from camdesk.capture import storage
from camdesk.capture.recorder import Recorder
from camdesk.capture.snapshot import SnapshotService
from camdesk.config.settings import Settings
from camdesk.core import messages
from camdesk.core.frames import VideoFrame
from camdesk.core.models import ConnectionState, RecordingState, Toast, ToastLevel
from camdesk.core.state import AppState

log = logging.getLogger(__name__)

ELAPSED_TICK_MS = 500
RECORDABLE_TRANSPORT = "rtsp"  # MJPEG fallback has no packets to save


class CaptureManager(QObject):
    def __init__(
        self,
        state: AppState,
        settings: Settings,
        latest_frame: Callable[[], VideoFrame | None],
        *,
        recorder: Recorder | None = None,
        snapshots: SnapshotService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.settings = settings
        self._latest_frame = latest_frame
        self.recorder = recorder or Recorder(self)
        self.snapshots = snapshots or SnapshotService(self)
        self._stream: Any = None
        self._started_at = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(ELAPSED_TICK_MS)
        self._tick.timeout.connect(self._update_elapsed)

        self.recorder.part_started.connect(self._on_part_started)
        self.recorder.stopped.connect(self._on_recorder_stopped)
        self.snapshots.saved.connect(self._on_snapshot_saved)
        self.snapshots.failed.connect(self._on_snapshot_failed)

    # -- stream lifecycle (from AppController) ---------------------------------

    def attach_stream(self, stream: Any) -> None:
        self._stream = stream

    def detach_stream(self) -> None:
        """The stream is going away (disconnect / other camera): finish any recording."""
        self.stop_recording()
        self._stream = None

    # -- snapshot ----------------------------------------------------------------

    def snapshot(self) -> None:
        frame = self._latest_frame()
        if frame is None:
            self._toast(messages.NO_FRAME_YET, ToastLevel.WARNING)
            return
        self.snapshots.take(frame, self.settings.snapshots_path())

    # -- recording -----------------------------------------------------------------

    @property
    def recording(self) -> bool:
        return self.recorder.active

    def toggle_recording(self) -> None:
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if self.recorder.busy:
            return  # recording, or still finishing the previous file (milliseconds)
        if self._stream is None or self.state.connection is not ConnectionState.CONNECTED:
            self._toast(messages.RECORDING_NOT_CONNECTED, ToastLevel.WARNING)
            return
        if self.state.stream_info.transport != RECORDABLE_TRANSPORT:
            self._toast(messages.RECORDING_NEEDS_MAIN_STREAM, ToastLevel.WARNING)
            return
        folder = self.settings.recordings_path()
        free = storage.free_bytes(folder)
        if free is not None and free < storage.LOW_DISK_STOP_BYTES:
            self._toast(messages.DISK_FULL.format(gb=free / storage.GB), ToastLevel.ERROR)
            return
        if free is not None and free < storage.LOW_DISK_WARN_BYTES:
            self._toast(messages.LOW_DISK_WARNING.format(gb=free / storage.GB), ToastLevel.WARNING)

        path = self.recorder.start(folder, self.settings.segment_minutes * 60)
        self._stream.add_packet_sink(self.recorder.push)
        self._started_at = time.monotonic()
        self.state.set_recording(RecordingState(active=True, part=1, path=str(path)))
        self._tick.start()
        log.info("Recording started: %s", path)
        self._toast(messages.RECORDING_STARTED.format(name=path.name), ToastLevel.INFO, folder)

    def stop_recording(self) -> None:
        """Returns at once; the file is finished on the recorder thread (then a toast)."""
        if not self.recording:
            return
        if self._stream is not None:
            self._stream.remove_packet_sink(self.recorder.push)
        self.recorder.stop(timeout_s=0)

    def shutdown(self) -> None:
        """App exit: finish the file before the process ends (blocking is fine here)."""
        if self._stream is not None:
            self._stream.remove_packet_sink(self.recorder.push)
        self.recorder.stop(timeout_s=5.0)
        self._tick.stop()

    # -- signals from worker threads (queued onto the UI thread) --------------------

    @Slot(int, str)
    def _on_part_started(self, part: int, path: str) -> None:
        r = self.state.recording
        if r.active:
            self.state.set_recording(RecordingState(True, r.elapsed_s, part, path))

    @Slot(str)
    def _on_recorder_stopped(self, reason: str) -> None:
        self._tick.stop()
        last = self.state.recording
        self.state.set_recording(RecordingState())
        if self._stream is not None:
            self._stream.remove_packet_sink(self.recorder.push)
        folder = self.settings.recordings_path()
        if reason:
            self._toast(reason, ToastLevel.ERROR, folder)
        elif last.path:
            name = Path(last.path).name
            self._toast(messages.RECORDING_SAVED.format(name=name), ToastLevel.SUCCESS, folder)

    @Slot(str, object)
    def _on_snapshot_saved(self, path: str, thumbnail: object) -> None:
        self.state.notify(
            Toast(
                messages.SNAPSHOT_SAVED.format(name=Path(path).name),
                ToastLevel.SUCCESS,
                action_path=path,
                thumbnail=thumbnail,
            )
        )

    @Slot(str)
    def _on_snapshot_failed(self, reason: str) -> None:
        self._toast(messages.SNAPSHOT_FAILED.format(reason=reason), ToastLevel.ERROR)

    def _update_elapsed(self) -> None:
        r = self.state.recording
        if r.active:
            elapsed = time.monotonic() - self._started_at
            self.state.set_recording(RecordingState(True, round(elapsed, 1), r.part, r.path))

    def _toast(self, message: str, level: ToastLevel, path: Path | None = None) -> None:
        self.state.notify(Toast(message, level, action_path=str(path) if path else ""))
