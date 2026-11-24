"""Where captures go and what they're called. Pure helpers + small filesystem checks."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

GB = 1_000_000_000
LOW_DISK_WARN_BYTES = 2 * GB  # warn before recording
LOW_DISK_STOP_BYTES = 1 * GB  # stop a running recording


def timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """folder/stem.suffix, or stem_2.suffix, stem_3… if it already exists."""
    candidate = folder / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{n}{suffix}"
        n += 1
    return candidate


def snapshot_path(folder: Path, now: datetime | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return unique_path(folder, f"snapshot_{timestamp(now)}", ".jpg")


def recording_base(folder: Path, now: datetime | None = None) -> Path:
    """Path without suffix; parts are <base>.mkv, <base>_part2.mkv, …"""
    folder.mkdir(parents=True, exist_ok=True)
    first = unique_path(folder, f"recording_{timestamp(now)}", ".mkv")
    return first.with_suffix("")


def part_path(base: Path, part: int) -> Path:
    return base.with_suffix(".mkv") if part == 1 else base.with_name(f"{base.name}_part{part}.mkv")


def free_bytes(path: Path) -> int | None:
    """Free space on the drive holding `path` (or its nearest existing parent)."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            try:
                return shutil.disk_usage(candidate).free
            except OSError:
                return None
    return None
