"""`--smoke-test`: verify a build end to end, then exit 0 (pass) or 1 (fail).

Used on the packaged CamDesk.exe, where tests can't reach inside: connect, wait for video,
take a snapshot, record a few seconds, check both files, quit. Results go to the log.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from camdesk.core.controller import AppController
from camdesk.core.models import ConnectionState

log = logging.getLogger(__name__)

TIMEOUT_S = 45
RECORD_S = 3


class SmokeTest(QObject):
    def __init__(self, app: QApplication, controller: AppController) -> None:
        super().__init__(controller)
        self._app = app
        self._c = controller
        self._started = time.monotonic()
        self._step = "waiting for video"
        self._record_started = 0.0
        self.failures: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        log.info("SMOKE TEST: started")
        self._timer.start()

    def _tick(self) -> None:
        c, state = self._c, self._c.state
        if time.monotonic() - self._started > TIMEOUT_S:
            self._finish(f"timed out while {self._step}")
            return
        if self._step == "waiting for video":
            if state.connection is ConnectionState.CONNECTED and state.stream_info.fps > 0:
                info = state.stream_info
                log.info(
                    "SMOKE TEST: video %dx%d %.1f fps, decoder %s",
                    info.width, info.height, info.fps, info.decoder,
                )  # fmt: skip
                c.capture.snapshot()
                c.capture.start_recording()
                self._record_started = time.monotonic()
                self._step = "recording"
        elif self._step == "recording":
            if time.monotonic() - self._record_started >= RECORD_S:
                c.capture.stop_recording()
                self._step = "finishing files"
        elif self._step == "finishing files" and not c.capture.recorder.busy:
            self._check_files()
            self._finish()

    def _check_files(self) -> None:
        settings = self._c.settings
        snaps = list(Path(settings.snapshots_path()).glob("snapshot_*.jpg"))
        recs = list(Path(settings.recordings_path()).glob("recording_*.mkv"))
        if not snaps or snaps[0].stat().st_size < 1000:
            self.failures.append("no snapshot saved")
        else:
            log.info(
                "SMOKE TEST: snapshot %s (%d KB)", snaps[0].name, snaps[0].stat().st_size // 1024
            )
        transport = self._c.state.stream_info.transport
        if transport == "rtsp":
            if not recs or recs[0].stat().st_size < 10_000:
                self.failures.append("no recording saved")
            else:
                log.info(
                    "SMOKE TEST: recording %s (%d KB)", recs[0].name, recs[0].stat().st_size // 1024
                )
        else:
            log.info("SMOKE TEST: recording skipped (transport %s has no packets)", transport)

    def _finish(self, error: str = "") -> None:
        self._timer.stop()
        if error:
            self.failures.append(error)
        if self.failures:
            log.error("SMOKE TEST: FAILED — %s", "; ".join(self.failures))
        else:
            log.info("SMOKE TEST: PASSED")
        self._app.exit(1 if self.failures else 0)
