from __future__ import annotations

import gc
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from camdesk.dev.fake_camera import FakeCamera


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test writes settings/logs/captures into its own temp folder."""
    monkeypatch.setenv("CAMDESK_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def collect_qt_garbage() -> Iterator[None]:
    """Collect each test's leftover Qt objects right after its teardown, while nothing runs.

    Without this, Python's GC destroys a previous test's windows/threads at a random moment
    in a later test — mid-stream, from inside a Qt slot — and Qt can abort the whole run
    ("Fatal Python error: Aborted"). Couldn't be reproduced in the app itself (40 camera
    switches with forced GC, old window collected while a new one streams): it's a test
    harness timing issue, so the fix lives here.
    """
    yield
    app = QApplication.instance()
    if app is not None:
        app.processEvents()  # run pending deleteLater()s first
    gc.collect()


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """One QApplication for the whole test run (widgets need QApplication, not QCoreApplication)."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def fake_camera() -> Iterator[FakeCamera]:
    with FakeCamera() as cam:
        yield cam
