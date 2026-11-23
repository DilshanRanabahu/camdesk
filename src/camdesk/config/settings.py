"""Load and save user settings as versioned JSON.

Passwords are never stored here — see config/secrets.py (keyring).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from camdesk.config import paths
from camdesk.core.models import DEFAULT_PORT, CameraProfile

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass(slots=True)
class WindowState:
    x: int | None = None
    y: int | None = None
    width: int = 1280
    height: int = 760
    maximized: bool = False
    side_panel_open: bool = True


@dataclass(slots=True)
class Settings:
    version: int = SCHEMA_VERSION
    cameras: list[CameraProfile] = field(default_factory=list)
    last_camera_id: str | None = None
    snapshots_dir: str | None = None  # None = default folder
    recordings_dir: str | None = None
    segment_minutes: int = 30
    window: WindowState = field(default_factory=WindowState)

    # -- helpers ---------------------------------------------------------

    def camera(self, camera_id: str | None) -> CameraProfile | None:
        return next((c for c in self.cameras if c.id == camera_id), None)

    @property
    def last_camera(self) -> CameraProfile | None:
        return self.camera(self.last_camera_id)

    def upsert_camera(self, profile: CameraProfile) -> None:
        """Add or replace a camera and make it the last used one."""
        self.cameras = [c for c in self.cameras if c.id != profile.id]
        self.cameras.insert(0, profile)  # most recent first
        self.last_camera_id = profile.id

    def remove_camera(self, camera_id: str) -> None:
        self.cameras = [c for c in self.cameras if c.id != camera_id]
        if self.last_camera_id == camera_id:
            self.last_camera_id = self.cameras[0].id if self.cameras else None

    def snapshots_path(self) -> Path:
        return Path(self.snapshots_dir) if self.snapshots_dir else paths.default_snapshots_dir()

    def recordings_path(self) -> Path:
        return Path(self.recordings_dir) if self.recordings_dir else paths.default_recordings_dir()


# -- serialization -------------------------------------------------------


def _pick(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only keys the dataclass knows, so old/new files don't crash loading."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def _from_dict(data: dict[str, Any]) -> Settings:
    cameras = []
    for raw in data.get("cameras", []):
        try:
            item = _pick(CameraProfile, raw)
            item["port"] = int(item.get("port", DEFAULT_PORT))
            cameras.append(CameraProfile(**item))
        except (TypeError, ValueError):
            log.warning("Skipping invalid camera entry in settings")
    window = WindowState(**_pick(WindowState, data.get("window", {})))
    rest = _pick(Settings, data)
    rest.pop("cameras", None)
    rest.pop("window", None)
    rest["version"] = SCHEMA_VERSION
    settings = Settings(cameras=cameras, window=window, **rest)
    if settings.segment_minutes < 1:
        settings.segment_minutes = 30
    return settings


def load(path: Path | None = None) -> Settings:
    """Load settings. Missing or broken files fall back to defaults (never crash)."""
    path = path or paths.settings_file()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings root is not an object")
        return _from_dict(data)
    except (OSError, ValueError, TypeError) as exc:
        backup = path.with_suffix(".broken.json")
        log.warning("Settings file unreadable (%s); backing up to %s", exc, backup.name)
        with contextlib.suppress(OSError):
            path.replace(backup)
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    """Write atomically: temp file + rename, so a crash never leaves half a file."""
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(settings), indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
