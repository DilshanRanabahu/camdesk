from __future__ import annotations

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


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """One QApplication for the whole test run (widgets need QApplication, not QCoreApplication)."""
    app = QApplication.instance()
    return app if isinstance(app, QApplication) else QApplication([])


@pytest.fixture
def fake_camera() -> Iterator[FakeCamera]:
    with FakeCamera() as cam:
        yield cam
