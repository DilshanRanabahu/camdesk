"""Design tokens from docs/ui-design.md. The only place colors, sizes and fonts are defined."""

from __future__ import annotations

# -- surfaces --------------------------------------------------------------
BG_BASE = "#0E0F12"
BG_SURFACE = "#16181D"
BG_ELEVATED = "#1E2128"
BG_HOVER = "#262A33"
BG_OVERLAY = "rgba(14, 15, 18, 0.72)"
BORDER = "#2A2E37"
VIDEO_LETTERBOX = "#000000"

# -- text --------------------------------------------------------------------
TEXT_PRIMARY = "#E8EAED"
TEXT_SECONDARY = "#9AA0AA"
TEXT_DISABLED = "#5C626C"
TEXT_ON_ACCENT = "#FFFFFF"

# -- accent & status -------------------------------------------------------
ACCENT = "#4C8DFF"
ACCENT_HOVER = "#6BA1FF"
SUCCESS = "#3DD68C"
WARNING = "#F5B544"
DANGER = "#FF4D5E"

# -- typography ------------------------------------------------------------
FONT_UI = "Segoe UI Variable"
FONT_UI_FALLBACK = "Segoe UI"
FONT_MONO = "Cascadia Mono"
FONT_MONO_FALLBACK = "Consolas"
SIZE_TITLE = 15
SIZE_BODY = 13
SIZE_LABEL = 12
SIZE_CAPTION = 11
SIZE_MONO = 12

# -- spacing & shape -------------------------------------------------------
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_6, SPACE_8 = 4, 8, 12, 16, 24, 32
RADIUS_SM = 6
RADIUS_MD = 10

# -- layout (px) -------------------------------------------------------------
TITLEBAR_HEIGHT = 44
STATUSBAR_HEIGHT = 28
WINDOW_BUTTON_WIDTH = 46
CONNECT_CARD_WIDTH = 380
WORDMARK_WIDTH = 240
CONTROL_HEIGHT = 36
ICON_SM = 16
ICON_MD = 18
ICON_LG = 22
STATUS_DOT = 8
RESIZE_BORDER = 6  # invisible resize margin of the frameless window
WINDOW_MIN_WIDTH = 960
WINDOW_MIN_HEIGHT = 600
DIM_OVERLAY = "rgba(0, 0, 0, 0.55)"  # darkens the last frame while reconnecting

# -- motion (ms) -------------------------------------------------------------
ANIM_FAST = 120
ANIM_BASE = 200


def hex_to_rgb_f(color: str) -> tuple[float, float, float]:
    """'#RRGGBB' -> (r, g, b) floats 0–1, for OpenGL clear colors."""
    c = color.lstrip("#")
    return int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255
