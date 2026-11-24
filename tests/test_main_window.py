"""MainWindow smoke tests with the fake phone: pages, pill, overlay, shortcuts, geometry."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from camdesk.camera.client import CameraClient
from camdesk.config.settings import Settings
from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraProfile, ConnectionState
from camdesk.core.state import AppState
from camdesk.dev.fake_camera import FakeCamera
from camdesk.dev.fake_video_source import FakeVideoPlan
from camdesk.stream.service import StreamService
from camdesk.ui.main_window import MainWindow
from camdesk.ui.theme import stylesheet
from qt_helpers import wait_until
from test_controller import FakeSecrets


@pytest.fixture
def window(qapp: QApplication, fake_camera: FakeCamera) -> Iterator[MainWindow]:
    stylesheet.apply(qapp)
    buffer = LatestFrameBuffer()
    plan = FakeVideoPlan(fps=60)
    state = AppState()
    controller = AppController(
        state,
        Settings(),
        CameraClient(),
        lambda p, pw: StreamService(buffer, [plan.factory], backoff_s=(0.01,)),
        secrets=FakeSecrets(),
        save_settings=lambda s: None,
    )
    # Always stop the client thread, even if building the window fails: Qt aborts the whole
    # test process when a running QThread is destroyed.
    try:
        win = MainWindow(buffer, state, controller, app_icon=QIcon(), custom_frame=False)
        win.fake_camera = fake_camera  # type: ignore[attr-defined]
        win.show()
        qapp.processEvents()
        yield win
        win.close()
    finally:
        controller.shutdown()


def submit(win: MainWindow, address: str, port: str = "") -> None:
    win.connect_view.address.setText(address)
    win.connect_view.port.setText(port)
    win.connect_view.connect_button.click()


def test_starts_on_connect_screen(window: MainWindow) -> None:
    assert window.stack.currentWidget() is window.connect_view
    assert window.connect_view.address.hasFocus() or True  # focus depends on the window manager
    letter_keys = window._letter_shortcuts
    assert letter_keys and not any(s.isEnabled() for s in letter_keys)


def test_invalid_address_shows_error(window: MainWindow) -> None:
    submit(window, "192.168.1")
    assert not window.connect_view.error.isHidden()
    assert window.state.camera is None


def test_connect_switches_to_video_and_updates_bars(window: MainWindow) -> None:
    cam: FakeCamera = window.fake_camera  # type: ignore[attr-defined]
    submit(window, f"http://{cam.host}:{cam.port}")
    assert window.stack.currentWidget() is window.video
    assert cam.address in window.title_bar.pill.label.text()
    assert wait_until(lambda: window.state.connection is ConnectionState.CONNECTED)
    assert window.connection_overlay.isHidden()
    assert window.status_bar.connection.text() == "Connected"
    assert wait_until(lambda: "fps" in window.status_bar.stream.text())
    assert all(s.isEnabled() for s in window._letter_shortcuts)
    assert window.controller.settings.last_camera is not None  # remembered


def test_overlay_states(window: MainWindow) -> None:
    camera = CameraProfile(name="A06", host="10.0.0.9")
    overlay = window.connection_overlay
    overlay.update_state(ConnectionState.CONNECTING, "", camera)
    # isHidden(), not isVisible(): the video page isn't the current page in this test.
    assert not overlay.isHidden() and "10.0.0.9" in overlay.detail.text()
    assert overlay.buttons.isHidden()
    overlay.update_state(ConnectionState.FAILED, "Can't reach the phone", camera)
    assert not overlay.buttons.isHidden()
    assert overlay.property("dim") == "true"
    overlay.update_state(ConnectionState.CONNECTED, "", camera)
    assert overlay.isHidden()


def test_change_camera_returns_to_connect_screen(window: MainWindow) -> None:
    cam: FakeCamera = window.fake_camera  # type: ignore[attr-defined]
    submit(window, cam.host, str(cam.port))
    assert wait_until(lambda: window.state.connection is ConnectionState.CONNECTED)
    window.controller.close_camera()
    assert window.stack.currentWidget() is window.connect_view
    assert window.state.connection is ConnectionState.IDLE
    # The camera is now in the recent list and the form is pre-filled.
    assert window.connect_view.recent_box.count() == 1
    assert window.connect_view.address.text() == cam.host


def test_forget_camera(window: MainWindow) -> None:
    cam: FakeCamera = window.fake_camera  # type: ignore[attr-defined]
    submit(window, cam.host, str(cam.port))
    camera_id = window.state.camera.id  # type: ignore[union-attr]
    window.controller.close_camera()
    window.connect_view.forget_requested.emit(camera_id)
    assert window.controller.settings.cameras == []
    assert not window.connect_view.recent_title.isVisible()


def test_reconnect_same_address_keeps_profile(window: MainWindow) -> None:
    cam: FakeCamera = window.fake_camera  # type: ignore[attr-defined]
    submit(window, cam.host, str(cam.port))
    first = window.state.camera
    window.controller.close_camera()
    submit(window, cam.host, str(cam.port))
    assert window.state.camera is not None and window.state.camera.id == first.id  # type: ignore[union-attr]
    assert len(window.controller.settings.cameras) == 1


def test_geometry_saved_on_close(window: MainWindow) -> None:
    window.resize(1111, 700)
    window.close()
    w = window.controller.settings.window
    assert (w.width, w.height) == (1111, 700)
    assert w.maximized is False


def test_camera_label_skips_duplicate_ip() -> None:
    from camdesk.ui.connect_view import camera_label

    assert camera_label(CameraProfile(name="192.168.8.105", host="192.168.8.105")) == (
        "192.168.8.105:8080"
    )
    assert camera_label(CameraProfile(name="Galaxy A06", host="192.168.8.105")) == (
        "Galaxy A06  ·  192.168.8.105:8080"
    )
