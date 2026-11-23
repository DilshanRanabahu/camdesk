from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication

from camdesk.camera import endpoints as ep
from camdesk.camera.client import CameraApi, CameraClient
from camdesk.core.errors import CameraAuthError, CameraError
from camdesk.dev.fake_camera import FakeCamera
from qt_helpers import SignalRecorder


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# -- CameraApi (sync) ------------------------------------------------------


def test_api_status_and_sensors(fake_camera: FakeCamera) -> None:
    fake_camera.battery = 96.0
    api = CameraApi(fake_camera.host, fake_camera.port)
    status, capabilities = api.status()
    assert status.video_size == "1920x1080"
    assert capabilities is not None and capabilities.has_torch
    assert api.sensors().battery_percent == pytest.approx(96.0)
    assert "/status.json?show_avail=1" in fake_camera.requests
    api.close()


def test_api_commands(fake_camera: FakeCamera) -> None:
    api = CameraApi(fake_camera.host, fake_camera.port)
    api.send(ep.torch(True))
    api.send(ep.zoom(40))
    api.send(ep.night_vision(True))
    assert fake_camera.state["torch"] == "on"
    assert fake_camera.state["zoom"] == "460"
    assert fake_camera.state["night_vision"] == "on"
    api.close()


def test_api_unreachable() -> None:
    api = CameraApi("127.0.0.1", _free_port())
    with pytest.raises(CameraError, match="Can't reach"):
        api.status()
    api.close()


def test_api_auth() -> None:
    with FakeCamera(username="me", password="pw") as cam:
        bad = CameraApi(cam.host, cam.port, "me", "wrong")
        with pytest.raises(CameraAuthError):
            bad.status()
        good = CameraApi(cam.host, cam.port, "me", "pw")
        assert good.status()[0].video_size == "1920x1080"
        bad.close()
        good.close()


def test_api_rejected_command(fake_camera: FakeCamera) -> None:
    api = CameraApi(fake_camera.host, fake_camera.port)
    with pytest.raises(CameraError, match="HTTP 404"):
        api.send(ep.setting("does_not_exist", "1"))
    api.close()


# -- CameraClient (threaded) ----------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def client(qapp: QCoreApplication) -> Iterator[CameraClient]:
    c = CameraClient()
    yield c
    c.close()


def test_client_connects_and_reports_status(client: CameraClient, fake_camera: FakeCamera) -> None:
    fake_camera.battery = 96.0
    reachable = SignalRecorder(client.reachable_changed)
    status = SignalRecorder(client.status_received)
    battery = SignalRecorder(client.device_info_received)
    client.connect_to(fake_camera.host, fake_camera.port)
    assert status.wait(3000)
    assert reachable.count == 1 and reachable[0][0] is True
    if battery.count == 0:
        assert battery.wait(3000)
    assert battery[0][0].battery_percent == pytest.approx(96.0)


def test_client_command_then_refresh(client: CameraClient, fake_camera: FakeCamera) -> None:
    status = SignalRecorder(client.status_received)
    client.connect_to(fake_camera.host, fake_camera.port)
    assert status.wait(3000)

    ok = SignalRecorder(client.command_succeeded)
    client.send(ep.torch(True))
    assert ok.wait(3000)
    while status.count < 2:  # refresh after command
        assert status.wait(3000)
    latest_status = status[status.count - 1][0]
    assert latest_status.torch is True


def test_client_reports_unreachable(client: CameraClient) -> None:
    reachable = SignalRecorder(client.reachable_changed)
    client.connect_to("127.0.0.1", _free_port())
    assert reachable.wait(5000)
    assert reachable[0][0] is False
    assert "reach" in reachable[0][1]


def test_client_command_failure(client: CameraClient, fake_camera: FakeCamera) -> None:
    client.connect_to(fake_camera.host, fake_camera.port)
    failed = SignalRecorder(client.command_failed)
    client.send(ep.setting("does_not_exist", "1"))
    assert failed.wait(3000)
    assert "404" in failed[0][1]


def test_client_auth_failure(client: CameraClient) -> None:
    with FakeCamera(username="me", password="pw") as cam:
        auth = SignalRecorder(client.auth_failed)
        client.connect_to(cam.host, cam.port, "me", "wrong")
        assert auth.wait(3000)
