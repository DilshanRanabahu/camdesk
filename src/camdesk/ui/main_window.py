"""MainWindow — custom title bar, connect screen ⇄ video, status bar (ui-design.md §5–6).

Talks only to AppController (actions) and AppState (signals).
Keys: Ctrl+D debug · F11/F/double-click fullscreen · Esc exit fullscreen · V view mode
Temporary camera keys until the control dock/side panel in step 7:
T flashlight · C switch camera · + / - zoom · N night vision · A autofocus · Ctrl+R retry
"""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QEvent, QPoint, QRect
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QMainWindow, QMenu, QStackedWidget, QVBoxLayout, QWidget

from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraProfile, ConnectionState, Toast
from camdesk.core.state import AppState
from camdesk.ui import strings
from camdesk.ui.connect_view import ConnectView, camera_label
from camdesk.ui.status_bar import STATE_COLORS, StatusBar
from camdesk.ui.theme import tokens
from camdesk.ui.title_bar import TitleBar
from camdesk.ui.video.connection_overlay import ConnectionOverlay
from camdesk.ui.video.overlays import DebugOverlay
from camdesk.ui.video.video_widget import VideoWidget, ViewMode
from camdesk.ui.win_frame import NativeFrame

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        buffer: LatestFrameBuffer,
        state: AppState,
        controller: AppController,
        *,
        app_icon: QIcon,
        wordmark: QPixmap | None = None,
        custom_frame: bool = True,
    ) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self.setWindowTitle(strings.APP_NAME)
        self.setMinimumSize(tokens.WINDOW_MIN_WIDTH, tokens.WINDOW_MIN_HEIGHT)
        self._maximized_before_fullscreen = False

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.title_bar = TitleBar(app_icon)
        self.stack = QStackedWidget()
        self.connect_view = ConnectView(wordmark)
        self.video = VideoWidget(buffer)
        self.connection_overlay = ConnectionOverlay(self.video)
        self.debug = DebugOverlay(self.video, buffer, state)
        self.stack.addWidget(self.connect_view)
        self.stack.addWidget(self.video)
        self.status_bar = StatusBar(controller.settings.recordings_path())
        layout.addWidget(self.title_bar)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.status_bar)
        self.setCentralWidget(root)

        self.frame = NativeFrame(self, tokens.RESIZE_BORDER, self._is_caption)
        if custom_frame:
            self.frame.enable()
        self.title_bar.show_window_buttons(self.frame.active)

        self._wire()
        self._restore_geometry()
        self._on_camera_changed(state.camera)
        self._on_connection_changed(state.connection, state.connection_message)

    # -- wiring --------------------------------------------------------------

    def _wire(self) -> None:
        s, c = self.state, self.controller
        s.frame_ready.connect(self.video.on_frame_ready)
        s.camera_changed.connect(self._on_camera_changed)
        s.connection_changed.connect(self._on_connection_changed)
        s.stream_info_changed.connect(self.status_bar.set_stream_info)
        s.device_info_changed.connect(self.status_bar.set_device_info)
        s.notification.connect(self._show_toast)

        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_toggled.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.pill.clicked.connect(self._show_camera_menu)

        self.connect_view.connect_requested.connect(self._connect_new)
        self.connect_view.recent_selected.connect(self._connect_saved)
        self.connect_view.forget_requested.connect(self._forget)
        self.connection_overlay.retry_requested.connect(c.retry)
        self.connection_overlay.change_camera_requested.connect(c.close_camera)
        self.video.double_clicked.connect(self.toggle_fullscreen)

        keys = {
            "Ctrl+D": self.debug.toggle,
            "F11": self.toggle_fullscreen,
            "F": self.toggle_fullscreen,
            "Esc": self.exit_fullscreen,
            "V": self.cycle_view_mode,
            "T": c.toggle_torch,
            "C": c.switch_camera,
            "+": c.zoom_in,
            "=": c.zoom_in,
            "-": c.zoom_out,
            "N": c.toggle_night_vision,
            "A": c.focus,
            "Ctrl+R": c.retry,
        }
        # Single-key shortcuts are switched off on the connect screen, so typing an address
        # like "192.168.1.5" doesn't trigger zoom or the flashlight.
        self._letter_shortcuts: list[QShortcut] = []
        for key, action in keys.items():
            shortcut = QShortcut(QKeySequence(key), self, action)
            if len(key) == 1:
                self._letter_shortcuts.append(shortcut)

    # -- state → UI ---------------------------------------------------------

    def _on_camera_changed(self, camera: CameraProfile | None) -> None:
        if camera is None:
            self.title_bar.pill.set_text(strings.NO_CAMERA)
            self.connect_view.set_cameras(self.controller.settings.cameras, None)
            self.stack.setCurrentWidget(self.connect_view)
            self.video.clear()
            self.connect_view.focus_address()
        else:
            self.title_bar.pill.set_text(camera_label(camera))
            self.stack.setCurrentWidget(self.video)
        for shortcut in self._letter_shortcuts:
            shortcut.setEnabled(camera is not None)

    def _on_connection_changed(self, state: ConnectionState, message: str) -> None:
        self.title_bar.pill.dot.set_color(STATE_COLORS[state])
        self.status_bar.set_connection(state, message)
        self.connection_overlay.update_state(state, message, self.state.camera)

    def _show_toast(self, toast: Toast) -> None:
        log.info("Notification: %s", toast.message)
        self.status_bar.show_message(toast.message)

    # -- actions --------------------------------------------------------------

    def _connect_new(self, host: str, port: int, username: str, password: str | None) -> None:
        known = self.controller.find_camera(host, port)
        profile = (
            replace(known, username=username)
            if known
            else CameraProfile(name=host, host=host, port=port, username=username)
        )
        self.controller.connect_camera(profile, password)

    def _connect_saved(self, camera_id: str) -> None:
        camera = self.controller.settings.camera(camera_id)
        if camera is not None:
            self.controller.connect_camera(camera)

    def _forget(self, camera_id: str) -> None:
        self.controller.forget_camera(camera_id)
        self.connect_view.set_cameras(self.controller.settings.cameras, None)

    def _show_camera_menu(self) -> None:
        menu = QMenu(self)
        current = self.state.camera
        cameras = self.controller.settings.cameras
        if cameras:
            header = menu.addAction(strings.MENU_RECENT)
            header.setEnabled(False)
            for camera in cameras[:8]:
                action = QAction(camera_label(camera), menu)
                action.setCheckable(True)
                action.setChecked(current is not None and camera.id == current.id)
                action.triggered.connect(lambda _=False, cid=camera.id: self._connect_saved(cid))
                menu.addAction(action)
            menu.addSeparator()
        menu.addAction(strings.MENU_CHANGE_CAMERA, self.controller.close_camera)
        disconnect = menu.addAction(strings.MENU_DISCONNECT, self.controller.disconnect)
        disconnect.setEnabled(self.state.connection is not ConnectionState.IDLE)
        pill = self.title_bar.pill
        menu.exec(pill.mapToGlobal(QPoint(0, pill.height() + tokens.SPACE_1)))

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._maximized_before_fullscreen = self.isMaximized()
            self.title_bar.hide()
            self.status_bar.hide()
            self.showFullScreen()

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.title_bar.show()
            self.status_bar.show()
            if self._maximized_before_fullscreen:
                self.showMaximized()
            else:
                self.showNormal()

    def cycle_view_mode(self) -> None:
        modes = list(ViewMode)
        self.video.set_view_mode(modes[(modes.index(self.video.view_mode) + 1) % len(modes)])

    # -- window frame & geometry ----------------------------------------------

    def _is_caption(self, pos: QPoint) -> bool:
        bar = self.title_bar
        if not bar.isVisible() or not bar.geometry().contains(pos):
            return False
        return bar.is_caption(bar.mapFrom(self, pos))

    def nativeEvent(self, event_type: object, message: object) -> tuple[bool, int]:  # noqa: N802
        if event_type == b"windows_generic_MSG" and self.frame.active:
            handled, result = self.frame.handle(int(message))  # type: ignore[call-overload]
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)  # type: ignore[arg-type]

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _restore_geometry(self) -> None:
        w = self.controller.settings.window
        self.resize(max(w.width, tokens.WINDOW_MIN_WIDTH), max(w.height, tokens.WINDOW_MIN_HEIGHT))
        screen = self.screen()
        if w.x is not None and w.y is not None:
            target = QRect(w.x, w.y, self.width(), self.height())
            # Only restore the position if it's still on a connected screen.
            if any(sc.availableGeometry().intersects(target) for sc in screen.virtualSiblings()):
                self.move(w.x, w.y)
                return
        center = screen.availableGeometry().center()
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    def show_restored(self) -> None:
        """Show with the saved maximized state."""
        if self.controller.settings.window.maximized:
            self.showMaximized()
        else:
            self.show()

    def closeEvent(self, event: QEvent) -> None:  # noqa: N802
        w = self.controller.settings.window
        w.maximized = self.isMaximized()
        if not (self.isMaximized() or self.isFullScreen()):
            geometry = self.geometry()
            w.x, w.y, w.width, w.height = (
                geometry.x(),
                geometry.y(),
                geometry.width(),
                geometry.height(),
            )
        super().closeEvent(event)
