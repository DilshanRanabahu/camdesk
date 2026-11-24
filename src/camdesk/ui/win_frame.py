"""Frameless window that still behaves like a native Windows window.

We draw our own title bar, but let Windows do the window management:
- the window keeps WS_CAPTION / WS_THICKFRAME, so Snap, Win+arrows, Aero shake,
  minimize/maximize animations and the drop shadow keep working;
- WM_NCCALCSIZE makes the client area cover the whole window (hides the native bar);
- WM_NCHITTEST tells Windows where the resize edges and the draggable caption are,
  so moving, resizing and double-click-to-maximize are handled natively.

Anything that fails here falls back silently to a normal window (`--native-frame` forces it).
"""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084

HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

_GWL_STYLE = -16
_WS_FRAME_BITS = 0x00C00000 | 0x00040000 | 0x00010000 | 0x00020000 | 0x00080000
# WS_CAPTION | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
_SWP_FLAGS = 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010
# SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
_SM_CXSIZEFRAME, _SM_CXPADDEDBORDER = 32, 92
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]  # fmt: skip


class _NcCalcSizeParams(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def hit_test(
    x: int, y: int, width: int, height: int, border: int, *, resizable: bool, in_caption: bool
) -> int:
    """Windows hit-test code for a point in window coordinates (logical px)."""
    if resizable:
        left, right = x < border, x >= width - border
        top, bottom = y < border, y >= height - border
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
    return HTCAPTION if in_caption else HTCLIENT


class NativeFrame:
    """Attach to a top-level window. Call `enable()` before show, route nativeEvent to `handle`."""

    def __init__(self, window: QWidget, border: int, is_caption: Callable[[QPoint], bool]) -> None:
        self.window = window
        self.border = border
        self.is_caption = is_caption
        self.active = False

    def enable(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            self.window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            hwnd = int(self.window.winId())
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
            user32.SetWindowLongW(hwnd, _GWL_STYLE, style | _WS_FRAME_BITS)
            dwm = ctypes.windll.dwmapi
            margins = _Margins(0, 0, 0, 1)  # a 1 px DWM frame gives the native drop shadow
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            for attribute, value in (
                (_DWMWA_USE_IMMERSIVE_DARK_MODE, 1),
                (_DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND),  # Windows 11 only
            ):
                v = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FLAGS)
        except (AttributeError, OSError):
            log.warning("Custom window frame unavailable; using the normal frame", exc_info=True)
            self.window.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
            return False
        self.active = True
        return True

    def handle(self, message: int) -> tuple[bool, int]:
        """Process a native message. Returns (handled, result) for QWidget.nativeEvent."""
        if not self.active:
            return False, 0
        msg = wintypes.MSG.from_address(message)
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            # Ask Windows, not Qt: during fullscreen -> maximized Qt still reports fullscreen,
            # the inset was skipped and ~7 px were cut off at every edge.
            if ctypes.windll.user32.IsZoomed(msg.hWnd):
                self._inset_maximized(msg)
            return True, 0  # client area = whole window: no native title bar or border
        if msg.message == WM_NCHITTEST:
            pos = self.window.mapFromGlobal(QCursor.pos())
            code = hit_test(
                pos.x(),
                pos.y(),
                self.window.width(),
                self.window.height(),
                self.border,
                resizable=not (self.window.isMaximized() or self.window.isFullScreen()),
                in_caption=not self.window.isFullScreen() and self.is_caption(pos),
            )
            return True, code
        return False, 0

    def _inset_maximized(self, msg: wintypes.MSG) -> None:
        """A maximized window hangs over the screen edge by its frame size; pull it back in."""
        user32 = ctypes.windll.user32
        hwnd = int(self.window.winId())
        dpi = user32.GetDpiForWindow(hwnd)
        thickness = user32.GetSystemMetricsForDpi(
            _SM_CXSIZEFRAME, dpi
        ) + user32.GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
        params = _NcCalcSizeParams.from_address(msg.lParam)
        rect = params.rgrc[0]
        rect.left += thickness
        rect.top += thickness
        rect.right -= thickness
        rect.bottom -= thickness
