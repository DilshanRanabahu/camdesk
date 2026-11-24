"""Step 9 polish: notices, toasts, settings dialog, view-mode memory, wheel zoom."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QIcon, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from camdesk.camera.client import CameraClient
from camdesk.config.settings import Settings
from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import (
    CameraProfile,
    ConnectionState,
    DeviceInfo,
    StreamInfo,
    Toast,
    ToastLevel,
)
from camdesk.core.notices import Notices
from camdesk.core.state import AppState
from camdesk.dev.fake_camera import FakeCamera
from camdesk.dev.fake_video_source import FakeVideoPlan
from camdesk.stream.service import StreamService
from camdesk.ui.main_window import MainWindow
from camdesk.ui.settings_dialog import SettingsDialog
from camdesk.ui.video.video_widget import ViewMode
from camdesk.ui.widgets import toast as toast_module
from camdesk.ui.widgets.toast import ToastHost
from qt_helpers import SignalRecorder, wait_until
from test_controller import FakeSecrets

# -- notices ---------------------------------------------------------------------------


def test_reconnected_only_after_a_real_drop(qapp: QApplication) -> None:
    state = AppState()
    notices = Notices(state)  # keep a reference: an unreferenced QObject is collected
    assert notices is not None
    toasts = SignalRecorder(state.notification)
    state.set_connection(ConnectionState.CONNECTING)
    state.set_connection(ConnectionState.RECONNECTING, "attempt 1")  # never had video yet
    state.set_connection(ConnectionState.CONNECTED)
    assert toasts.count == 0
    state.set_stream_info(StreamInfo(width=1920, height=1080))
    state.set_connection(ConnectionState.RECONNECTING, "Wi-Fi dropped")
    state.set_connection(ConnectionState.CONNECTED)
    assert toasts.count == 1 and toasts[0][0].message == "Reconnected"


def test_low_battery_warns_once(qapp: QApplication) -> None:
    state = AppState()
    notices = Notices(state)  # keep a reference: an unreferenced QObject is collected
    assert notices is not None
    toasts = SignalRecorder(state.notification)
    state.set_device_info(DeviceInfo(battery_percent=19, charging=False))
    state.set_device_info(DeviceInfo(battery_percent=18, charging=False))
    assert toasts.count == 1 and "19%" in toasts[0][0].message
    state.set_device_info(DeviceInfo(battery_percent=18, charging=True))  # plugged in: reset
    state.set_device_info(DeviceInfo(battery_percent=17, charging=False))
    assert toasts.count == 2


def test_no_battery_reported_no_warning(qapp: QApplication) -> None:
    state = AppState()
    notices = Notices(state)  # keep a reference: an unreferenced QObject is collected
    assert notices is not None
    toasts = SignalRecorder(state.notification)
    state.set_device_info(DeviceInfo())  # the A06 reports nothing
    assert toasts.count == 0


# -- toasts ---------------------------------------------------------------------------


@pytest.fixture
def host(qapp: QApplication) -> Iterator[ToastHost]:
    parent = QWidget()
    parent.resize(900, 600)
    parent.show()
    h = ToastHost(parent)
    yield h
    parent.close()


def test_toast_stack_limit_and_dedupe(host: ToastHost) -> None:
    for i in range(5):
        host.show_toast(Toast(f"message {i}"))
    live = [c for c in host.cards if not c._closing]
    assert len(live) == 3 and live[-1].toast.message == "message 4"
    host.show_toast(Toast("message 4"))  # same text again: no duplicate card
    assert len([c for c in host.cards if not c._closing]) == 3


def test_toast_auto_dismiss(host: ToastHost, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toast_module, "DURATION_MS", 50)
    host.show_toast(Toast("short"))
    assert host.isVisible()
    assert wait_until(lambda: not host.cards, 2000)
    assert not host.isVisible()


def test_toast_action_and_thumbnail(host: ToastHost, tmp_path: Path) -> None:
    image = QImage(160, 90, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    card = host.show_toast(
        Toast("Snapshot saved", ToastLevel.SUCCESS, action_path=str(tmp_path), thumbnail=image)
    )
    assert card.action.text() == "Open"
    thumb = card.findChild(type(card.label), "ToastThumb")
    assert thumb is not None and thumb.pixmap().height() == 48


def test_error_toasts_stay_longer() -> None:
    assert (
        toast_module.DURATION_ERROR_MS > toast_module.DURATION_ACTION_MS > toast_module.DURATION_MS
    )


# -- settings dialog ----------------------------------------------------------------------


def test_settings_dialog_apply(qapp: QApplication, tmp_path: Path) -> None:
    settings = Settings()
    defaults = Settings()
    dialog = SettingsDialog(settings, defaults.snapshots_path(), defaults.recordings_path())
    dialog.recordings.edit.setText(str(tmp_path / "rec"))
    dialog.part_minutes.setValue(15)
    dialog.apply()
    assert settings.recordings_dir == str(tmp_path / "rec")
    assert settings.snapshots_dir is None  # unchanged default stays "follow the default"
    assert settings.segment_minutes == 15
    dialog.recordings.edit.setText(str(defaults.recordings_path()))
    dialog.apply()
    assert settings.recordings_dir is None


# -- main window: view mode memory, wheel zoom, toasts on screen --------------------------


@pytest.fixture
def window(qapp: QApplication, fake_camera: FakeCamera) -> Iterator[MainWindow]:
    buffer = LatestFrameBuffer()
    plan = FakeVideoPlan(fps=60)
    state = AppState()
    settings = Settings()
    settings.view_mode = "fill"
    controller = AppController(
        state,
        settings,
        CameraClient(),
        lambda p, pw: StreamService(buffer, [plan.factory], backoff_s=(0.01,)),
        secrets=FakeSecrets(),
        save_settings=lambda s: None,
        latest_frame=buffer.peek,
    )
    try:
        win = MainWindow(buffer, state, controller, app_icon=QIcon(), custom_frame=False)
        win.resize(1300, 800)
        win.show()
        controller.connect_camera(
            CameraProfile(name="F", host=fake_camera.host, port=fake_camera.port)
        )
        assert wait_until(lambda: state.connection is ConnectionState.CONNECTED)
        assert wait_until(lambda: state.capabilities.has_zoom)
        yield win
        win.close()
    finally:
        controller.shutdown()


def test_view_mode_remembered(window: MainWindow) -> None:
    assert window.video.view_mode is ViewMode.FILL  # restored from settings
    assert window.side_panel.view_buttons[ViewMode.FILL].isChecked()
    window.cycle_view_mode()
    assert window.controller.settings.view_mode == "original"


def test_wheel_zooms(window: MainWindow) -> None:
    video = window.video
    center = QPointF(video.width() / 2, video.height() / 2)
    event = QWheelEvent(
        center,
        video.mapToGlobal(center),
        QPoint(0, 0),
        QPoint(0, 240),  # two notches up
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(video, event)
    assert window.state.camera_status.zoom_ratio == pytest.approx(1.5)


def test_notifications_appear_as_toasts(window: MainWindow) -> None:
    window.state.notify(Toast("Hello", ToastLevel.INFO))
    assert window.toasts.isVisible() and window.toasts.cards[-1].label.text() == "Hello"
    # Toasts sit above the dock, not on top of it.
    assert (
        window.toasts.geometry().bottom()
        < window.dock.mapTo(window.centralWidget(), QPoint(0, 0)).y()
    )


def test_failed_overlay_has_hint(window: MainWindow) -> None:
    overlay = window.connection_overlay
    overlay.update_state(ConnectionState.FAILED, "Can't reach the phone", window.state.camera)
    assert "IP Webcam" in overlay.detail.text()
