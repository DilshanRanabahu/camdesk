from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from camdesk.dev.fake_camera import FakeCamera


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test writes settings/logs/captures into its own temp folder."""
    monkeypatch.setenv("CAMDESK_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_camera() -> Iterator[FakeCamera]:
    with FakeCamera() as cam:
        yield cam
