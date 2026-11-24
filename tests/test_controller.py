"""AppController end-to-end: real CameraClient + StreamService, fake phone and fake video."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from PySide6.QtWidgets import QApplication

from camdesk.camera.client import CameraClient
from camdesk.config.settings import Settings
from camdesk.core.controller import AppController
from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import CameraFacing, CameraProfile, ConnectionState, ToastLevel
from camdesk.core.state import AppState
from camdesk.dev.fake_camera import FakeCamera
from camdesk.dev.fake_video_source import FakeVideoPlan
from camdesk.stream.service import StreamService
from qt_helpers import SignalRecorder, wait_until


@dataclass
class FakeSecrets:
    store: dict[str, str] = field(default_factory=dict)

    def get_password(self, camera_id: str) -> str:
        return self.store.get(camera_id, "")

    def set_password(self, camera_id: str, password: str) -> None:
        self.store[camera_id] = password

    def delete_password(self, camera_id: str) -> None:
        self.store.pop(camera_id, None)


@dataclass
class Rig:
    state: AppState
    controller: AppController
    camera: FakeCamera
    profile: CameraProfile
    secrets: FakeSecrets
    saved: list[Settings]
    streams: list[tuple[CameraProfile, str]]
    buffer: LatestFrameBuffer


@pytest.fixture
def rig(qapp: QApplication, fake_camera: FakeCamera) -> Iterator[Rig]:
    buffer = LatestFrameBuffer()
    streams: list[tuple[CameraProfile, str]] = []
    plan = FakeVideoPlan(fps=60)

    def make_stream(profile: CameraProfile, password: str) -> StreamService:
        streams.append((profile, password))
        return StreamService(buffer, [plan.factory], backoff_s=(0.01,))

    saved: list[Settings] = []
    secrets = FakeSecrets()
    state = AppState()
    controller = AppController(
        state,
        Settings(),
        CameraClient(),
        make_stream,
        secrets=secrets,
        save_settings=saved.append,
    )
    profile = CameraProfile(name="Fake A06", host=fake_camera.host, port=fake_camera.port)
    yield Rig(state, controller, fake_camera, profile, secrets, saved, streams, buffer)
    controller.shutdown()


def connect(rig: Rig) -> None:
    rig.controller.connect_camera(rig.profile)
    assert wait_until(lambda: rig.state.connection is ConnectionState.CONNECTED)
    assert wait_until(lambda: rig.state.capabilities.has_torch)  # first status arrived


def test_connect_streams_and_reads_capabilities(rig: Rig) -> None:
    frames = SignalRecorder(rig.state.frame_ready)
    connect(rig)
    assert rig.state.camera == rig.profile
    assert rig.state.capabilities.zoom_max_ratio == pytest.approx(10.0)
    assert wait_until(lambda: frames.count > 0)
    assert rig.buffer.take() is not None
    assert wait_until(lambda: rig.state.stream_info.fps > 0)


def test_connect_remembers_camera(rig: Rig) -> None:
    connect(rig)
    assert rig.controller.settings.last_camera == rig.profile
    assert wait_until(lambda: len(rig.saved) == 1)  # saved on a worker thread
    assert rig.saved[0].last_camera == rig.profile


def test_password_saved_and_passed_to_stream(rig: Rig) -> None:
    profile = CameraProfile(name="A06", host=rig.camera.host, port=rig.camera.port, username="me")
    rig.controller.connect_camera(profile, "pw")
    assert rig.secrets.store[profile.id] == "pw"
    assert rig.streams[-1] == (profile, "pw")
    rig.controller.connect_camera(profile)  # no password given -> uses the saved one
    assert rig.streams[-1] == (profile, "pw")


def test_fake_mode_does_not_remember(rig: Rig) -> None:
    rig.controller.connect_camera(rig.profile, "pw", remember=False)
    assert rig.controller.settings.cameras == []
    assert rig.secrets.store == {}


def test_torch_is_optimistic_then_confirmed(rig: Rig) -> None:
    connect(rig)
    rig.controller.toggle_torch()
    assert rig.state.camera_status.torch is True  # immediately, before the phone answers
    assert wait_until(lambda: rig.camera.state["torch"] == "on")


def test_switch_camera_updates_capabilities(rig: Rig) -> None:
    connect(rig)
    rig.controller.set_torch(True)
    assert wait_until(lambda: rig.camera.state["torch"] == "on")
    rig.controller.switch_camera()
    assert rig.state.camera_status.facing is CameraFacing.FRONT
    assert rig.state.camera_status.torch is False
    assert wait_until(lambda: not rig.state.capabilities.has_torch)  # front camera: no flash
    assert not rig.state.capabilities.has_autofocus


def test_unavailable_control_warns_instead_of_sending(rig: Rig) -> None:
    connect(rig)
    rig.controller.switch_camera()
    assert wait_until(lambda: not rig.state.capabilities.has_torch)
    toasts = SignalRecorder(rig.state.notification)
    before = len(rig.camera.requests)
    rig.controller.set_torch(True)
    assert toasts.count == 1 and toasts[0][0].level is ToastLevel.WARNING
    assert "Flashlight" in toasts[0][0].message
    wait_until(lambda: False, timeout_ms=100)
    assert not any("torch" in r for r in rig.camera.requests[before:])


def test_zoom_is_throttled_and_lands_on_last_value(rig: Rig) -> None:
    connect(rig)
    before = len(rig.camera.requests)
    for step in range(1, 21):  # simulate a fast slider drag to 3.0×
        rig.controller.set_zoom(1.0 + step * 0.1)
    assert rig.state.camera_status.zoom_ratio == pytest.approx(3.0)
    # The phone zooms in steps: 3.0× is sent as 22% -> "298" (2.98×), like the real A06.
    expected = str(100 + 9 * rig.state.capabilities.zoom_percent(3.0))
    assert expected == "298"
    assert wait_until(lambda: rig.camera.state["zoom"] == expected)
    sent = [r for r in rig.camera.requests[before:] if r.startswith("/ptz")]
    assert 1 <= len(sent) <= 3  # 20 slider moves -> a couple of commands


def test_zoom_is_clamped(rig: Rig) -> None:
    connect(rig)
    rig.controller.set_zoom(50.0)
    assert rig.state.camera_status.zoom_ratio == pytest.approx(10.0)
    rig.controller.zoom_out()
    assert rig.state.camera_status.zoom_ratio == pytest.approx(9.5)


def test_failed_command_shows_error_and_reverts(rig: Rig) -> None:
    connect(rig)
    toasts = SignalRecorder(rig.state.notification)
    rig.controller.set_video_size("640x480")
    rig.camera.state.pop("video_size")  # make the phone reject /settings/video_size
    rig.controller.set_orientation("portrait")  # still works
    rig.controller.set_video_size("1280x720")
    assert wait_until(lambda: any(t[0].level is ToastLevel.ERROR for t in toasts.calls))
    error = next(t[0] for t in toasts.calls if t[0].level is ToastLevel.ERROR)
    assert error.message.startswith("Resolution failed")


def test_disconnect_returns_immediately_and_resets(rig: Rig) -> None:
    connect(rig)
    rig.controller.set_torch(True)
    rig.controller.disconnect()
    assert rig.state.connection is ConnectionState.IDLE
    assert rig.state.camera_status.torch is False  # camera data cleared
    assert rig.state.stream_info.fps == 0


def test_reconnect_to_new_camera_ignores_old_stream(rig: Rig) -> None:
    connect(rig)
    other = CameraProfile(name="Other", host=rig.camera.host, port=rig.camera.port)
    states = SignalRecorder(rig.state.connection_changed)
    rig.controller.connect_camera(other)
    assert rig.state.camera == other
    assert wait_until(lambda: rig.state.connection is ConnectionState.CONNECTED)
    # IDLE (disconnect) -> CONNECTING -> CONNECTED; no stray states from the old stream
    names = [c[0] for c in states.calls]
    assert names[0] is ConnectionState.IDLE
    assert names[-1] is ConnectionState.CONNECTED
    assert len(rig.streams) == 2
