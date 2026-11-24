"""User-facing text produced by the core layer (toasts). English only.

UI text lives in ui/strings.py; core can't import ui/, so its own messages live here.
"""

from __future__ import annotations

COMMAND_FAILED = "{label} failed: {reason}"
WRONG_PASSWORD = "Wrong username or password for {camera}"
CAMERA_UNREACHABLE = "Can't reach {camera}. Is IP Webcam running? The phone's IP may have changed."
CONNECTED = "Connected to {camera}"
NOT_AVAILABLE = "{label} is not available on this camera"
SETTINGS_SAVE_FAILED = "Couldn't save settings: {reason}"
