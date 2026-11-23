"""Qt test helpers.

QSignalSpy.wait() in PySide6 keeps the Python GIL while it waits, which stops Python slots
on worker threads from running. SignalRecorder waits with a QEventLoop instead, which
releases the GIL like app.exec() does in the real app.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEventLoop, QTimer, SignalInstance


class SignalRecorder:
    """Records every emission of a signal. Index it like a list of argument tuples."""

    def __init__(self, signal: SignalInstance) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._loop: QEventLoop | None = None
        signal.connect(self._record)

    def _record(self, *args: Any) -> None:
        self.calls.append(args)
        if self._loop is not None:
            self._loop.quit()

    @property
    def count(self) -> int:
        return len(self.calls)

    def __getitem__(self, index: int) -> tuple[Any, ...]:
        return self.calls[index]

    def wait(self, timeout_ms: int = 3000) -> bool:
        """Wait for the next emission. Returns False on timeout."""
        before = self.count
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self._loop = loop
        timer.start(timeout_ms)
        loop.exec()
        timer.stop()
        self._loop = None
        return self.count > before
