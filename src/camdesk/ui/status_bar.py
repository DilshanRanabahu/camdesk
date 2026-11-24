"""Bottom status bar: connection · battery · disk space · stream info (ui-design.md §5)."""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from camdesk.core.models import ConnectionState, DeviceInfo, StreamInfo
from camdesk.ui import strings
from camdesk.ui.theme import tokens
from camdesk.ui.title_bar import StatusDot

DISK_REFRESH_MS = 30_000
MESSAGE_MS = 4000

STATE_COLORS = {
    ConnectionState.IDLE: tokens.TEXT_DISABLED,
    ConnectionState.CONNECTING: tokens.WARNING,
    ConnectionState.CONNECTED: tokens.SUCCESS,
    ConnectionState.RECONNECTING: tokens.WARNING,
    ConnectionState.FAILED: tokens.DANGER,
}
STATE_TEXT = {
    ConnectionState.IDLE: strings.IDLE,
    ConnectionState.CONNECTING: strings.CONNECTING,
    ConnectionState.CONNECTED: strings.CONNECTED,
    ConnectionState.RECONNECTING: strings.RECONNECTING,
    ConnectionState.FAILED: strings.FAILED,
}


def free_space_gb(path: Path) -> float | None:
    """Free space on the drive that holds `path` (or its nearest existing parent)."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            try:
                return shutil.disk_usage(candidate).free / 1e9
            except OSError:
                return None
    return None


class StatusBar(QWidget):
    def __init__(self, captures_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(tokens.STATUSBAR_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._captures_dir = captures_dir

        layout = QHBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_3, 0, tokens.SPACE_3, 0)
        layout.setSpacing(tokens.SPACE_3)
        self.dot = StatusDot()
        self.connection = QLabel(strings.IDLE)
        self.battery = QLabel()
        self.disk = QLabel()
        self.stream = QLabel()
        self.message = QLabel()
        self.message.setTextFormat(Qt.TextFormat.RichText)
        self.message.linkActivated.connect(self._open_link)
        self.rec = QLabel()
        self.rec.setObjectName("StatusRec")
        self.rec.hide()
        layout.addWidget(self.dot)
        layout.addWidget(self.connection)
        layout.addWidget(self.battery)
        layout.addWidget(self.disk)
        layout.addWidget(self.rec)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.stream)
        self.battery.hide()

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self.message.clear)
        self._disk_timer = QTimer(self)
        self._disk_timer.setInterval(DISK_REFRESH_MS)
        self._disk_timer.timeout.connect(self.refresh_disk)
        self._disk_timer.start()
        self.refresh_disk()

    def set_connection(self, state: ConnectionState, message: str = "") -> None:
        self.dot.set_color(STATE_COLORS[state])
        text = STATE_TEXT[state]
        if message and state in (ConnectionState.RECONNECTING, ConnectionState.FAILED):
            text = f"{text} {message}"
        self.connection.setText(text)
        if state is not ConnectionState.CONNECTED:
            self.stream.clear()

    def set_device_info(self, info: DeviceInfo) -> None:
        if info.battery_percent is None:
            self.battery.hide()  # IP Webcam on the A06 reports no battery
            return
        template = strings.STATUS_BATTERY_CHARGING if info.charging else strings.STATUS_BATTERY
        self.battery.setText(template.format(percent=info.battery_percent))
        self.battery.show()

    def set_stream_info(self, info: StreamInfo) -> None:
        if not info.width:
            self.stream.clear()
            return
        self.stream.setText(
            strings.STATUS_STREAM.format(
                width=info.width, height=info.height, fps=info.fps, decoder=info.decoder
            )
        )

    def show_message(self, text: str, path: str = "") -> None:
        """Short-lived message (until real toasts arrive in step 9), with an "Open" link."""
        safe = html.escape(text)
        if path:
            url = QUrl.fromLocalFile(path).toString()
            safe += f' · <a href="{url}" style="color:{tokens.ACCENT}">{strings.OPEN_LINK}</a>'
        self.message.setText(safe)
        self._message_timer.start(MESSAGE_MS * (2 if path else 1))

    def set_recording(self, active: bool, elapsed: str) -> None:
        self.rec.setVisible(active)
        if active:
            self.rec.setText(strings.STATUS_RECORDING.format(elapsed=elapsed))

    def _open_link(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def set_captures_dir(self, folder: Path) -> None:
        self._captures_dir = folder
        self.refresh_disk()

    def refresh_disk(self) -> None:
        gb = free_space_gb(self._captures_dir)
        self.disk.setText(strings.STATUS_DISK_FREE.format(gb=gb) if gb is not None else "")
