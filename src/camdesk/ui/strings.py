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
CHANGE_CAMERA = "Change camera"

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
