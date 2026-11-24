"""All user-facing text (English). Keep wording here so it stays consistent."""

from __future__ import annotations

APP_NAME = "CamDesk"

# Connection states
CONNECTING = "Connecting…"
CONNECTED = "Connected"
RECONNECTING = "Reconnecting…"
FAILED = "Connection failed"
IDLE = "Not connected"
CONNECTING_TO = "Connecting to {address}…"

# Title bar
CAMERA_LABEL = "{name}  ·  {address}"
NO_CAMERA = "No camera"
MENU_RECENT = "Recent cameras"
MENU_CHANGE_CAMERA = "Change camera…"
MENU_DISCONNECT = "Disconnect"
TIP_MINIMIZE = "Minimize"
TIP_MAXIMIZE = "Maximize"
TIP_RESTORE = "Restore"
TIP_CLOSE = "Close"
TIP_CAMERA_PILL = "Switch or change camera"

# Connect screen
CONNECT_SUBTITLE = "Connect to your phone camera"
FIELD_ADDRESS = "IP address"
FIELD_PORT = "Port"
FIELD_USERNAME = "Username"
FIELD_PASSWORD = "Password"
PLACEHOLDER_ADDRESS = "192.168.1.5"
PLACEHOLDER_PASSWORD_SAVED = "Saved — leave empty to keep"
LOGIN_TOGGLE = "Login (optional)"
CONNECT_BUTTON = "Connect"
RECENT_TITLE = "Recent"
TIP_FORGET = "Forget this camera"
CONNECT_HINT = "On the phone: open IP Webcam and tap Start server. Use the address it shows."

# Connection overlay
RETRY = "Retry"
FAILED_HINT = "Is IP Webcam running on the phone? Its IP address may have changed."
CHANGE_CAMERA = "Change camera"

# Control dock (tooltips show the shortcut)
TIP_SNAPSHOT = "Snapshot · Space"
TIP_RECORD = "Record · R"
TIP_SWITCH_CAMERA = "Switch camera · C"
TIP_FOCUS = "Focus · A (or click the picture)"
TIP_FULLSCREEN = "Fullscreen · F"
TIP_COMING_SOON = "Coming soon"
TIP_STOP_RECORD = "Stop recording · R"

# Side panel
PANEL_CAMERA = "Camera"
PANEL_IMAGE = "Image"
PANEL_VIEW = "View"
FLASHLIGHT = "Flashlight"
NIGHT_VISION = "Night vision"
ZOOM = "Zoom"
ZOOM_VALUE = "{ratio:.1f}×"
QUALITY = "Quality"
QUALITY_VALUE = "{value}%"
RESOLUTION = "Resolution"
ROTATE = "Rotate"
TIP_ROTATE_LEFT = "Rotate left"
TIP_ROTATE_RIGHT = "Rotate right"
MIRROR = "Mirror"
FLIP = "Flip vertically"
VIEW_FIT = "Fit"
VIEW_FILL = "Fill"
VIEW_ORIGINAL = "1:1"
TIP_VIEW = "View mode · V"
TIP_PANEL = "Show / hide controls · Tab"
NOT_ON_THIS_CAMERA = "Not available on this camera"
ORIENTATION_NAMES = {
    "landscape": "Landscape",
    "portrait": "Portrait",
    "upsidedown": "Upside down",
    "upsidedown_portrait": "Portrait (flipped)",
}

# Captures card
PANEL_CAPTURES = "Captures"
OPEN_SNAPSHOTS = "Open snapshots folder"
OPEN_RECORDINGS = "Open recordings folder"

# Recording badge
REC_BADGE = "●  REC  {elapsed}"
REC_BADGE_PART = "●  REC  {elapsed} · Part {part}"
STATUS_RECORDING = "● REC {elapsed}"
OPEN_LINK = "Open"

# Settings dialog
SETTINGS_TITLE = "Settings"
TIP_SETTINGS = "Settings · Ctrl+,"
SETTINGS_CAPTURES = "Captures"
SETTINGS_SNAPSHOTS_FOLDER = "Snapshots folder"
SETTINGS_RECORDINGS_FOLDER = "Recordings folder"
SETTINGS_BROWSE = "Browse…"
SETTINGS_RESET = "Default"
SETTINGS_PART_LENGTH = "Start a new recording file every"
SETTINGS_MINUTES = " min"
SETTINGS_SHORTCUTS = "Keyboard shortcuts"
SETTINGS_SAVE = "Save"
SETTINGS_CANCEL = "Cancel"
SHORTCUTS = (
    ("Space", "Snapshot"),
    ("R", "Start / stop recording"),
    ("F  ·  F11  ·  double-click", "Fullscreen (Esc exits)"),
    ("T", "Flashlight"),
    ("C", "Switch camera"),
    ("+  /  −  ·  mouse wheel", "Zoom"),
    ("N", "Night vision"),
    ("A  ·  click the picture", "Focus"),
    ("V", "View mode: fit / fill / 1:1"),
    ("Tab", "Show / hide side panel"),
    ("Ctrl+R", "Retry connection"),
    ("Ctrl+D", "Debug overlay"),
    ("Ctrl+,", "Settings"),
)

# Status bar
STATUS_BATTERY = "Battery {percent:.0f}%"
STATUS_BATTERY_CHARGING = "Battery {percent:.0f}% · charging"
STATUS_DISK_FREE = "{gb:.0f} GB free"
STATUS_STREAM = "{width}×{height} · {fps:.0f} fps · {decoder}"

# Debug overlay
DEBUG_TITLE = "DEBUG  (Ctrl+D)"
DEBUG_RENDER_FPS = "Render"
DEBUG_STREAM_FPS = "Stream"
DEBUG_RESOLUTION = "Video"
DEBUG_DECODER = "Decoder"
DEBUG_TRANSPORT = "Source"
DEBUG_BITRATE = "Bitrate"
DEBUG_FRAME_AGE = "Frame age"
DEBUG_DROPPED = "Dropped"
DEBUG_CPU = "CPU"
DEBUG_NO_DATA = "—"
DEBUG_CAMERA = "Camera"
DEBUG_TORCH = "Torch"
DEBUG_NIGHT = "Night"
DEBUG_PHONE = "Phone"
DEBUG_FRONT = "front"
DEBUG_BACK = "back"
DEBUG_ON = "on"
DEBUG_OFF = "off"
DEBUG_UNAVAILABLE = "n/a"
