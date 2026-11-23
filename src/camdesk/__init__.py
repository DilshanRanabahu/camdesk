"""CamDesk — view, record and control an Android IP Webcam from Windows."""

from __future__ import annotations

__version__ = "0.1.0"


def main() -> None:
    from camdesk.app import run

    raise SystemExit(run())
