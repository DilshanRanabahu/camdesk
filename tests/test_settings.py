from __future__ import annotations

import json
from pathlib import Path

from camdesk.config import paths
from camdesk.config import settings as store
from camdesk.core.models import CameraProfile


def test_missing_file_gives_defaults() -> None:
    s = store.load()
    assert s.cameras == []
    assert s.segment_minutes == 30
    assert s.last_camera is None


def test_round_trip(isolated_home: Path) -> None:
    s = store.Settings()
    cam = CameraProfile(name="Galaxy A06", host="192.168.8.105", username="me")
    s.upsert_camera(cam)
    s.window.width = 1500
    store.save(s)

    loaded = store.load()
    assert loaded.last_camera == cam
    assert loaded.window.width == 1500
    assert paths.settings_file().is_relative_to(isolated_home)


def test_password_never_written() -> None:
    s = store.Settings()
    s.upsert_camera(CameraProfile(name="A06", host="10.0.0.2", username="me"))
    store.save(s)
    text = paths.settings_file().read_text(encoding="utf-8")
    assert "password" not in text.lower()


def test_upsert_moves_to_front_and_remove_updates_last() -> None:
    s = store.Settings()
    a = CameraProfile(name="A", host="1.1.1.1")
    b = CameraProfile(name="B", host="2.2.2.2")
    s.upsert_camera(a)
    s.upsert_camera(b)
    assert [c.name for c in s.cameras] == ["B", "A"]
    s.remove_camera(b.id)
    assert s.last_camera == a


def test_broken_file_is_backed_up() -> None:
    f = paths.settings_file()
    f.parent.mkdir(parents=True)
    f.write_text("{not json", encoding="utf-8")
    s = store.load()
    assert s.cameras == []
    assert f.with_suffix(".broken.json").exists()


def test_unknown_and_invalid_fields_are_ignored() -> None:
    f = paths.settings_file()
    f.parent.mkdir(parents=True)
    data = {
        "version": 1,
        "future_option": True,
        "cameras": [
            {"name": "ok", "host": "1.2.3.4", "port": "8080", "id": "x", "extra": 1},
            {"name": "bad"},  # missing host
        ],
        "window": {"width": 900, "unknown": 1},
        "segment_minutes": 0,
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    s = store.load()
    assert [c.name for c in s.cameras] == ["ok"]
    assert s.cameras[0].port == 8080
    assert s.window.width == 900
    assert s.segment_minutes == 30


def test_capture_dirs_default_and_override(tmp_path: Path) -> None:
    s = store.Settings()
    assert s.recordings_path() == paths.default_recordings_dir()
    s.recordings_dir = str(tmp_path / "rec")
    assert s.recordings_path() == tmp_path / "rec"
