"""Where CamDesk stores its data on disk.

Set the CAMDESK_HOME environment variable to redirect everything (used by tests).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "CamDesk"


def _override() -> Path | None:
    value = os.environ.get("CAMDESK_HOME")
    return Path(value) if value else None


def app_data_dir() -> Path:
    """%APPDATA%\\CamDesk — settings and logs."""
    if (home := _override()) is not None:
        return home / "appdata"
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def settings_file() -> Path:
    return app_data_dir() / "settings.json"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def default_captures_dir() -> Path:
    """%USERPROFILE%\\Videos\\CamDesk — snapshots and recordings."""
    if (home := _override()) is not None:
        return home / "captures"
    return Path.home() / "Videos" / APP_NAME


def default_snapshots_dir() -> Path:
    return default_captures_dir() / "Snapshots"


def default_recordings_dir() -> Path:
    return default_captures_dir() / "Recordings"


def resources_dir() -> Path:
    """Bundled images (icon, wordmark). Ships in the package; not affected by CAMDESK_HOME."""
    return Path(__file__).resolve().parent.parent / "resources"


def app_icon() -> Path:
    return resources_dir() / "app.ico"
