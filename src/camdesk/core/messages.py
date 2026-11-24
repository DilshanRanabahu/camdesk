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

# Connection & device
RECONNECTED = "Reconnected"
BATTERY_LOW = "Phone battery low ({percent:.0f}%) — plug it in to keep streaming"
UNEXPECTED_ERROR = "Something went wrong — details are in the log"

# Snapshots & recording
SNAPSHOT_SAVED = "Snapshot saved · {name}"
SNAPSHOT_FAILED = "Snapshot failed: {reason}"
NO_FRAME_YET = "No picture yet — wait for the video to start"
RECORDING_STARTED = "Recording · {name}"
RECORDING_SAVED = "Recording saved · {name}"
RECORDING_NEEDS_MAIN_STREAM = (
    "Recording needs the main video stream (not available on the backup stream)"
)
RECORDING_NOT_CONNECTED = "Connect to a camera to record"
LOW_DISK_WARNING = "Only {gb:.1f} GB free — recording uses about 7 GB per hour"
DISK_FULL = "Not enough disk space to record ({gb:.1f} GB free)"

# Address validation (connect screen)
ADDRESS_EMPTY = "Enter the phone's IP address"
ADDRESS_INVALID = "That doesn't look like an IP address (example: 192.168.1.5)"
PORT_INVALID = "Port must be a number from 1 to 65535"
