"""Small line icons (Lucide style: 24×24, round stroke), recolored to theme tokens at runtime.

Drawn inline so there are no icon files to ship. Add new ones to ICONS.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from camdesk.ui.theme import tokens

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    "{body}</svg>"
)

ICONS = {
    "minimize": '<path d="M6 12h12"/>',
    "maximize": '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
    "restore": '<rect x="5" y="9" width="10" height="10" rx="1.5"/><path d="M9 9V6.5A1.5 1.5 0 0 1 10.5 5h7A1.5 1.5 0 0 1 19 6.5v7a1.5 1.5 0 0 1-1.5 1.5H15"/>',  # noqa: E501
    "close": '<path d="M7 7l10 10M17 7L7 17"/>',
    "chevron-down": '<path d="m7 10 5 5 5-5"/>',
    "chevron-right": '<path d="m10 7 5 5-5 5"/>',
    "retry": '<path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.5"/><path d="M20 4v4.5h-4.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16.5v-5M12 8h.01"/>',
    "camera": '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.5-2h5L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.5"/>',  # noqa: E501
    "x-small": '<path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>',
    "record": '<circle cx="12" cy="12" r="6.5"/>',
    "switch-camera": '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.5-2h5L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><path d="M9.3 12.2a2.8 2.8 0 0 1 4.9-1.3"/><path d="M14.7 13.8a2.8 2.8 0 0 1-4.9 1.3"/><path d="M14.4 9.2v1.9h-1.9M9.6 16.8v-1.9h1.9"/>',  # noqa: E501
    "focus": '<path d="M4 8.5v-3A1.5 1.5 0 0 1 5.5 4h3M15.5 4h3A1.5 1.5 0 0 1 20 5.5v3M20 15.5v3a1.5 1.5 0 0 1-1.5 1.5h-3M8.5 20h-3A1.5 1.5 0 0 1 4 18.5v-3"/><circle cx="12" cy="12" r="2.5"/>',  # noqa: E501
    "fullscreen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "flashlight": '<path d="M8 3h8v4l-2 3v10a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1V10L8 7zM8 7h8M12 13v2"/>',  # noqa: E501
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "zoom": '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.3-4.3"/>',
    "rotate-ccw": '<path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/>',
    "rotate-cw": '<path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.5"/><path d="M20 4v4.5h-4.5"/>',
    "mirror": '<path d="M12 3v18"/><path d="M8.5 7.5 4 12l4.5 4.5zM15.5 7.5 20 12l-4.5 4.5z"/>',
    "flip": '<path d="M3 12h18"/><path d="M7.5 8.5 12 4l4.5 4.5zM7.5 15.5 12 20l4.5-4.5z"/>',
    "sidebar": '<rect x="4" y="5" width="16" height="14" rx="1.5"/><path d="M15 5v14"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "alert-triangle": '<path d="M10.3 4.2 2.8 17.5A2 2 0 0 0 4.5 20.5h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0zM12 9.5v4M12 17h.01"/>',  # noqa: E501
    "alert-circle": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16.5h.01"/>',
    "settings": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',  # noqa: E501
}


@lru_cache(maxsize=128)
def pixmap(name: str, size: int, color: str = tokens.TEXT_PRIMARY, ratio: float = 1.0) -> QPixmap:
    svg = _SVG.format(color=color, body=ICONS[name]).encode()
    renderer = QSvgRenderer(QByteArray(svg))
    physical = round(size * ratio)
    pm = QPixmap(physical, physical)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, physical, physical))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, size: int = tokens.ICON_MD, color: str = tokens.TEXT_PRIMARY) -> QIcon:
    """A QIcon with crisp 1× and 2× renders (for 100–200% Windows scaling)."""
    result = QIcon()
    for ratio in (1.0, 2.0):
        result.addPixmap(pixmap(name, size, color, ratio))
        # Explicit dimmed version: Qt's automatic one barely differs on a dark theme.
        result.addPixmap(pixmap(name, size, tokens.TEXT_DISABLED, ratio), QIcon.Mode.Disabled)
    return result


def icon_size(size: int = tokens.ICON_MD) -> QSize:
    return QSize(size, size)
