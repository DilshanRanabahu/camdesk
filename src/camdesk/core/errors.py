"""App-specific exceptions."""

from __future__ import annotations


class CamDeskError(Exception):
    """Base class for all CamDesk errors."""


class CameraError(CamDeskError):
    """The phone could not be reached or rejected a command."""


class CameraAuthError(CameraError):
    """The phone rejected the username/password."""


class StreamError(CamDeskError):
    """The video stream could not be opened or broke."""


class SettingsError(CamDeskError):
    """Settings could not be loaded or saved."""
