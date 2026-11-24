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
    return result


def icon_size(size: int = tokens.ICON_MD) -> QSize:
    return QSize(size, size)
