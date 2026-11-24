"""Connection states drawn over the video (ui-design.md §6.2).

CONNECTING   → "Connecting to 192.168.8.105…"
RECONNECTING → last frame dimmed + "Reconnecting… (attempt 2)"
FAILED       → message + Retry / Change camera
CONNECTED / IDLE → hidden
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from camdesk.core.models import CameraProfile, ConnectionState
from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens


class ConnectionOverlay(QWidget):
    retry_requested = Signal()
    change_camera_requested = Signal()

    def __init__(self, video: QWidget) -> None:
        super().__init__(video)
        self.setObjectName("ConnectionOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._video = video
        video.installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        panel = QFrame()
        panel.setObjectName("OverlayPanel")
        row.addWidget(panel)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(tokens.SPACE_6, tokens.SPACE_4, tokens.SPACE_6, tokens.SPACE_4)
        layout.setSpacing(tokens.SPACE_3)
        self.title = QLabel()
        self.title.setProperty("role", "title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel()
        self.detail.setProperty("role", "secondary")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setMaximumWidth(tokens.CONNECT_CARD_WIDTH)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)

        self.buttons = QWidget()
        buttons = QHBoxLayout(self.buttons)
        buttons.setContentsMargins(0, tokens.SPACE_2, 0, 0)
        buttons.setSpacing(tokens.SPACE_2)
        retry = QPushButton(strings.RETRY)
        retry.setProperty("variant", "primary")
        retry.setIcon(icons.icon("retry", tokens.ICON_SM, tokens.TEXT_ON_ACCENT))
        retry.clicked.connect(self.retry_requested)
        change = QPushButton(strings.CHANGE_CAMERA)
        change.setProperty("variant", "ghost")
        change.clicked.connect(self.change_camera_requested)
        buttons.addStretch(1)
        buttons.addWidget(retry)
        buttons.addWidget(change)
        buttons.addStretch(1)
        layout.addWidget(self.buttons)
        self.hide()

    def update_state(
        self, state: ConnectionState, message: str, camera: CameraProfile | None
    ) -> None:
        if state in (ConnectionState.CONNECTED, ConnectionState.IDLE):
            self.hide()
            return
        address = camera.address if camera else ""
        if state is ConnectionState.CONNECTING:
            self.title.setText(strings.CONNECTING)
            self.detail.setText(strings.CONNECTING_TO.format(address=address))
        elif state is ConnectionState.RECONNECTING:
            self.title.setText(strings.RECONNECTING)
            self.detail.setText(message)
        else:
            self.title.setText(strings.FAILED)
            hint = strings.FAILED_HINT
            self.detail.setText(f"{message}\n{hint}" if message else hint)
        self.detail.setVisible(bool(self.detail.text()))
        self.buttons.setVisible(state is ConnectionState.FAILED)
        dim = state in (ConnectionState.RECONNECTING, ConnectionState.FAILED)
        self.setProperty("dim", "true" if dim else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setGeometry(self._video.rect())
        self.show()
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._video and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._video.rect())
        return False
