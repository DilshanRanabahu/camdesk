"""Step 7 controls: controller actions on the fake phone, widgets, side panel and dock."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from camdesk.camera.client import CameraClient
from camdesk.config.settings import Settings
from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraProfile, ConnectionState, ToastLevel
from camdesk.core.state import AppState
from camdesk.dev.fake_camera import FakeCamera
from camdesk.dev.fake_video_source import FakeVideoPlan
from camdesk.stream.service import StreamService
from camdesk.ui.main_window import MainWindow
from camdesk.ui.theme import stylesheet
from camdesk.ui.video.video_widget import ViewMode
from camdesk.ui.widgets.slider import LabeledSlider
from camdesk.ui.widgets.toggle import ToggleSwitch
from qt_helpers import SignalRecorder, wait_until
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
    try:
        win = MainWindow(buffer, state, controller, app_icon=QIcon(), custom_frame=False)
        win.resize(1300, 800)
        win.show()
        controller.connect_camera(
            CameraProfile(name="Fake", host=fake_camera.host, port=fake_camera.port)
        )
        assert wait_until(lambda: state.connection is ConnectionState.CONNECTED)
        assert wait_until(lambda: state.capabilities.has_torch)
        win.fake = fake_camera  # type: ignore[attr-defined]
        yield win
        win.close()
    finally:
        controller.shutdown()


# -- controller ------------------------------------------------------------------


def test_rotate_mirror_flip_reach_the_phone(window: MainWindow) -> None:
    c, cam = window.controller, window.fake  # type: ignore[attr-defined]
    c.rotate(1)
    assert window.state.camera_status.orientation == "portrait"  # optimistic
    assert wait_until(lambda: cam.state["orientation"] == "portrait")
    c.rotate(-1)
    assert wait_until(lambda: cam.state["orientation"] == "landscape")
    c.toggle_mirror()
    assert wait_until(lambda: cam.state["mirror_flip"] == "mirror")
    c.toggle_flip()
    assert wait_until(lambda: cam.state["mirror_flip"] == "mirror,flip")
    c.toggle_mirror()
    assert wait_until(lambda: cam.state["mirror_flip"] == "flip")


def test_tap_to_focus_sends_region_then_focus(window: MainWindow) -> None:
    cam = window.fake  # type: ignore[attr-defined]
    before = cam.focus_requests
    window.controller.focus_at(0.75, 0.25)
    assert wait_until(lambda: cam.state["focus_region"] == "500x-500")
    assert wait_until(lambda: cam.focus_requests == before + 1)


def test_tap_to_focus_on_front_camera_warns(window: MainWindow) -> None:
    window.controller.switch_camera()
    assert wait_until(lambda: not window.state.capabilities.has_autofocus)
    toasts = SignalRecorder(window.state.notification)
    window.controller.focus_at(0.5, 0.5)
    assert toasts.count == 1 and toasts[0][0].level is ToastLevel.WARNING


# -- widgets ---------------------------------------------------------------------


def test_toggle_silent_update_does_not_emit(qapp: QApplication) -> None:
    toggle = ToggleSwitch()
    rec = SignalRecorder(toggle.toggled)
    toggle.set_checked_silently(True)
    assert toggle.isChecked() and rec.count == 0
    toggle.click()
    assert not toggle.isChecked() and rec.count == 1


def test_slider_commits_on_keyboard_and_ignores_silent(qapp: QApplication) -> None:
    slider = LabeledSlider("Quality", 1, 100, lambda v: f"{v}%")
    committed = SignalRecorder(slider.value_committed)
    slider.set_value_silently(40)
    assert committed.count == 0 and slider.value_label.text() == "40%"
    slider.slider.setValue(55)  # like an arrow key: not a drag, so it commits at once
    assert committed.count == 1 and committed[0][0] == 55


# -- side panel ------------------------------------------------------------------


def test_panel_reflects_phone_state(window: MainWindow) -> None:
    panel, cam = window.side_panel, window.fake  # type: ignore[attr-defined]
    assert panel.torch.isEnabled() and panel.zoom.isEnabled()
    assert panel.zoom.slider.maximum() == 100  # 10.0× in tenths
    assert panel.resolution.count() == 3
    cam.state["torch"] = "on"  # changed on the phone itself
    window.controller._client.refresh()
    assert wait_until(lambda: panel.torch.isChecked())


def test_panel_toggle_sends_command(window: MainWindow) -> None:
    window.side_panel.torch.click()
    assert wait_until(lambda: window.fake.state["torch"] == "on")  # type: ignore[attr-defined]


def test_panel_disables_what_the_camera_cannot_do(window: MainWindow) -> None:
    window.controller.switch_camera()
    panel = window.side_panel
    assert wait_until(lambda: not panel.torch.isEnabled())
    assert panel.torch_row.toolTip() == "Not available on this camera"
    assert not window.dock.focus.isEnabled()
    assert panel.zoom.isEnabled()  # the front camera still zooms


def test_controls_disabled_when_disconnected(window: MainWindow) -> None:
    window.controller.disconnect()
    assert not window.side_panel.torch.isEnabled()
    assert not window.side_panel.quality.isEnabled()
    assert not window.dock.switch.isEnabled()


def test_panel_visibility_rules(window: MainWindow) -> None:
    assert window.side_panel.isVisible()
    window._update_side_panel()
    window.toggle_side_panel()
    assert not window.side_panel.isVisible()
    assert window.controller.settings.window.side_panel_open is False
    window.toggle_side_panel()
    window.resize(1000, 700)  # narrow window: auto-hide
    assert wait_until(lambda: not window.side_panel.isVisible())
    window.resize(1300, 800)
    assert wait_until(lambda: window.side_panel.isVisible())


def test_view_mode_buttons(window: MainWindow) -> None:
    window.side_panel.view_buttons[ViewMode.FILL].click()
    assert window.video.view_mode is ViewMode.FILL
    window.cycle_view_mode()
    assert window.side_panel.view_buttons[ViewMode.ORIGINAL].isChecked()


def test_dock_buttons(window: MainWindow) -> None:
    dock = window.dock
    assert dock.snapshot.isEnabled() and dock.record.isEnabled()
    dock.switch.click()
    assert wait_until(lambda: window.fake.state["ffc"] == "on")  # type: ignore[attr-defined]


def test_picture_point_maps_letterbox(window: MainWindow) -> None:
    video = window.video
    assert wait_until(lambda: video.has_frame)
    w, h = video.width(), video.height()
    center = video.picture_point(QPoint(w // 2, h // 2))
    assert center is not None and center == pytest.approx((0.5, 0.5), abs=0.02)
    window.video.set_view_mode(ViewMode.FIT)
    video.resize(1600, 400)  # very wide: 640x360 picture is pillarboxed left/right
    assert video.picture_point(QPoint(5, 200)) is None


def test_fast_toggles_are_not_undone_by_stale_reports(window: MainWindow) -> None:
    """Real-phone bug: a status report already on its way undid the first toggle, so the
    second click computed from a stale value and the phone ended with mirror still on."""
    c, cam = window.controller, window.fake  # type: ignore[attr-defined]
    c.toggle_mirror()
    c.toggle_flip()
    assert wait_until(lambda: cam.state["mirror_flip"] == "mirror,flip")
    for _ in range(3):  # stale reports racing with the next clicks
        c._client.refresh()
        c.toggle_mirror()
        c._client.refresh()
        c.toggle_mirror()
    c._client.refresh()
    c.toggle_mirror()
    c.toggle_flip()
    assert wait_until(lambda: cam.state["mirror_flip"] == "none")
    assert wait_until(lambda: window.state.camera_status.mirror_flip == "none")
