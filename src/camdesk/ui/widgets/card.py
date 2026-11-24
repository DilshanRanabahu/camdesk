"""Card (ui-design.md §7) and a labeled row helper."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from camdesk.ui.theme import icons, tokens


class Card(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(tokens.SPACE_3, tokens.SPACE_3, tokens.SPACE_3, tokens.SPACE_3)
        self.body.setSpacing(tokens.SPACE_3)
        heading = QLabel(title.upper())
        heading.setProperty("role", "caption")
        self.body.addWidget(heading)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget


def row(text: str, control: QWidget, icon_name: str | None = None) -> QWidget:
    """[icon] Label ............ control"""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.SPACE_2)
    if icon_name:
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap(icon_name, tokens.ICON_SM, tokens.TEXT_SECONDARY))
        layout.addWidget(glyph)
    label = QLabel(text)
    layout.addWidget(label)
    layout.addStretch(1)
    layout.addWidget(control)
    widget.label = label  # type: ignore[attr-defined]  # for disabled styling / tooltips
    return widget
