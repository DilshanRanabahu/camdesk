"""Custom title bar: app icon + name, camera selector pill, window buttons (ui-design.md §5)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens


def _transparent_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


class StatusDot(QLabel):
    """A small round dot whose color shows the connection state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(tokens.STATUS_DOT, tokens.STATUS_DOT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.set_color(tokens.TEXT_DISABLED)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background:{color}; border-radius:{tokens.STATUS_DOT // 2}px;")


class CameraPill(QPushButton):
    """[● Galaxy A06 · 192.168.8.105 ▾] — opens the camera menu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", "pill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(strings.TIP_CAMERA_PILL)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_3, 0, tokens.SPACE_2, 0)
        layout.setSpacing(tokens.SPACE_2)
        self.dot = StatusDot()
        self.label = _transparent_label(strings.NO_CAMERA)
        chevron = _transparent_label()
        chevron.setPixmap(icons.pixmap("chevron-down", tokens.ICON_SM, tokens.TEXT_SECONDARY))
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addWidget(chevron)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        self.setMinimumWidth(self.layout().sizeHint().width())


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_toggled = Signal()
    close_requested = Signal()

    def __init__(self, app_icon: QIcon, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(tokens.TITLEBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_3, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_2)

        logo = _transparent_label()
        logo.setPixmap(app_icon.pixmap(tokens.ICON_LG, tokens.ICON_LG))
        name = _transparent_label(strings.APP_NAME)
        name.setObjectName("AppName")
        self.pill = CameraPill()

        layout.addWidget(logo)
        layout.addWidget(name)
        layout.addSpacing(tokens.SPACE_4)
        layout.addWidget(self.pill)
        layout.addStretch(1)

        self._buttons: list[QPushButton] = []
        self.min_button = self._window_button("minimize", strings.TIP_MINIMIZE, "window")
        self.max_button = self._window_button("maximize", strings.TIP_MAXIMIZE, "window")
        self.close_button = self._window_button("close", strings.TIP_CLOSE, "window-close")
        self.min_button.clicked.connect(self.minimize_requested)
        self.max_button.clicked.connect(self.maximize_toggled)
        self.close_button.clicked.connect(self.close_requested)
        for button in self._buttons:
            layout.addWidget(button)

    def _window_button(self, icon_name: str, tip: str, variant: str) -> QPushButton:
        button = QPushButton()
        button.setProperty("variant", variant)
        button.setIcon(icons.icon(icon_name, tokens.ICON_SM))
        button.setIconSize(icons.icon_size(tokens.ICON_SM))
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._buttons.append(button)
        return button

    def show_window_buttons(self, visible: bool) -> None:
        """Hidden when Windows draws its own title bar (`--native-frame`)."""
        for button in self._buttons:
            button.setVisible(visible)

    def set_maximized(self, maximized: bool) -> None:
        name, tip = (
            ("restore", strings.TIP_RESTORE) if maximized else ("maximize", strings.TIP_MAXIMIZE)
        )
        self.max_button.setIcon(icons.icon(name, tokens.ICON_SM))
        self.max_button.setToolTip(tip)

    def is_caption(self, pos: QPoint) -> bool:
        """True where dragging should move the window: empty space and plain labels."""
        widget = self.childAt(pos)
        while widget is not None and widget is not self:
            if isinstance(widget, QPushButton):
                return False
            widget = widget.parentWidget()
        return True
