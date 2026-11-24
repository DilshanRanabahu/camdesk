"""First-launch / connect screen (ui-design.md §6.1)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from camdesk.core.models import CameraProfile
from camdesk.core.validation import AddressError, parse_address
from camdesk.ui import strings
from camdesk.ui.theme import icons, tokens


def camera_label(camera: CameraProfile) -> str:
    """ "Galaxy A06  ·  192.168.8.105:8080", or just the address when the name is the IP."""
    if camera.name in (camera.host, camera.address):
        return camera.address
    return strings.CAMERA_LABEL.format(name=camera.name, address=camera.address)


def _label(text: str, role: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", role)
    return label


class ConnectView(QWidget):
    #: host, port, username, password (None = use the saved password)
    connect_requested = Signal(str, int, str, object)
    recent_selected = Signal(str)  # camera id
    forget_requested = Signal(str)  # camera id

    def __init__(self, wordmark: QPixmap | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectPage")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card.setFixedWidth(tokens.CONNECT_CARD_WIDTH)
        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(tokens.SPACE_6, tokens.SPACE_6, tokens.SPACE_6, tokens.SPACE_6)
        layout.setSpacing(tokens.SPACE_3)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if wordmark is not None and not wordmark.isNull():
            ratio = self.devicePixelRatioF()
            pm = wordmark.scaledToWidth(
                round(tokens.WORDMARK_WIDTH * ratio), Qt.TransformationMode.SmoothTransformation
            )
            pm.setDevicePixelRatio(ratio)
            logo.setPixmap(pm)
        else:
            logo.setText(strings.APP_NAME)
            logo.setProperty("role", "title")
        subtitle = _label(strings.CONNECT_SUBTITLE, "secondary")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addWidget(subtitle)
        layout.addSpacing(tokens.SPACE_2)

        # Address + port
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.SPACE_2)
        grid.setVerticalSpacing(tokens.SPACE_1)
        self.address = QLineEdit()
        self.address.setPlaceholderText(strings.PLACEHOLDER_ADDRESS)
        self.port = QLineEdit("8080")
        self.port.setValidator(QIntValidator(1, 65535, self))
        self.port.setFixedWidth(tokens.CONTROL_HEIGHT * 2 + tokens.SPACE_4)
        grid.addWidget(_label(strings.FIELD_ADDRESS, "label"), 0, 0)
        grid.addWidget(_label(strings.FIELD_PORT, "label"), 0, 1)
        grid.addWidget(self.address, 1, 0)
        grid.addWidget(self.port, 1, 1)
        layout.addLayout(grid)

        # Optional login
        self.login_toggle = QPushButton(strings.LOGIN_TOGGLE)
        self.login_toggle.setProperty("variant", "link")
        self.login_toggle.setCheckable(True)
        self.login_toggle.setIcon(
            icons.icon("chevron-right", tokens.ICON_SM, tokens.TEXT_SECONDARY)
        )
        self.login_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_toggle.toggled.connect(self._show_login)
        layout.addWidget(self.login_toggle)
        self.login_box = QWidget()
        login = QGridLayout(self.login_box)
        login.setContentsMargins(0, 0, 0, 0)
        login.setHorizontalSpacing(tokens.SPACE_2)
        login.setVerticalSpacing(tokens.SPACE_1)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        login.addWidget(_label(strings.FIELD_USERNAME, "label"), 0, 0)
        login.addWidget(_label(strings.FIELD_PASSWORD, "label"), 0, 1)
        login.addWidget(self.username, 1, 0)
        login.addWidget(self.password, 1, 1)
        self.login_box.hide()
        layout.addWidget(self.login_box)

        self.error = _label("", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        self.connect_button = QPushButton(strings.CONNECT_BUTTON)
        self.connect_button.setProperty("variant", "primary")
        self.connect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connect_button.setDefault(True)
        self.connect_button.clicked.connect(self._submit)
        layout.addWidget(self.connect_button)
        for field in (self.address, self.port, self.username, self.password):
            field.returnPressed.connect(self._submit)
            field.textEdited.connect(self._clear_error)

        # Recent cameras
        self.recent_title = _label(strings.RECENT_TITLE, "label")
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(tokens.SPACE_1)
        layout.addSpacing(tokens.SPACE_2)
        layout.addWidget(self.recent_title)
        layout.addLayout(self.recent_box)

        hint_row = QHBoxLayout()
        hint_row.setSpacing(tokens.SPACE_2)
        info = QLabel()
        info.setPixmap(icons.pixmap("info", tokens.ICON_SM, tokens.TEXT_SECONDARY))
        info.setAlignment(Qt.AlignmentFlag.AlignTop)
        hint = _label(strings.CONNECT_HINT, "caption")
        hint.setWordWrap(True)
        hint_row.addWidget(info)
        hint_row.addWidget(hint, 1)
        layout.addSpacing(tokens.SPACE_2)
        layout.addLayout(hint_row)

        self._recent_ids: list[str] = []

    # -- public ------------------------------------------------------------

    def set_cameras(self, cameras: list[CameraProfile], current: CameraProfile | None) -> None:
        """Fill the recent list and pre-fill the form with the last camera."""
        while self.recent_box.count():
            item = self.recent_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for camera in cameras[:5]:
            self.recent_box.addWidget(self._recent_row(camera))
        self.recent_title.setVisible(bool(cameras))
        last = current or (cameras[0] if cameras else None)
        if last is not None:
            self.address.setText(last.host)
            self.port.setText(str(last.port))
            self.username.setText(last.username)
            self.password.setPlaceholderText(
                strings.PLACEHOLDER_PASSWORD_SAVED if last.username else ""
            )
            self.login_toggle.setChecked(bool(last.username))

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()

    def focus_address(self) -> None:
        self.address.setFocus()
        self.address.selectAll()

    # -- internals ---------------------------------------------------------

    def _recent_row(self, camera: CameraProfile) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_1)
        button = QPushButton(camera_label(camera))
        button.setProperty("variant", "recent")
        button.setIcon(icons.icon("camera", tokens.ICON_SM, tokens.TEXT_SECONDARY))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False, cid=camera.id: self.recent_selected.emit(cid))
        forget = QPushButton()
        forget.setProperty("variant", "icon")
        forget.setIcon(icons.icon("x-small", tokens.ICON_SM, tokens.TEXT_SECONDARY))
        forget.setToolTip(strings.TIP_FORGET)
        forget.clicked.connect(lambda _=False, cid=camera.id: self.forget_requested.emit(cid))
        layout.addWidget(button, 1)
        layout.addWidget(forget)
        return row

    def _show_login(self, visible: bool) -> None:
        self.login_box.setVisible(visible)
        name = "chevron-down" if visible else "chevron-right"
        self.login_toggle.setIcon(icons.icon(name, tokens.ICON_SM, tokens.TEXT_SECONDARY))

    def _set_invalid(self, invalid: bool) -> None:
        self.address.setProperty("invalid", "true" if invalid else "false")
        self.address.style().unpolish(self.address)
        self.address.style().polish(self.address)

    def _clear_error(self) -> None:
        self.error.hide()
        self._set_invalid(False)

    def _submit(self) -> None:
        try:
            host, port = parse_address(self.address.text(), self.port.text())
        except AddressError as exc:
            self._set_invalid(True)
            self.show_error(str(exc))
            self.focus_address()
            return
        self._clear_error()
        username = self.username.text().strip() if self.login_toggle.isChecked() else ""
        password = self.password.text() if username else ""
        self.connect_requested.emit(host, port, username, password or None)
