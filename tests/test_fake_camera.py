from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

import pytest

from camdesk.dev.fake_camera import FakeCamera


def get(cam: FakeCamera, path: str, auth: tuple[str, str] | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(f"http://{cam.address}{path}")
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_status_with_avail(fake_camera: FakeCamera) -> None:
    code, body = get(fake_camera, "/status.json?show_avail=1")
    data = json.loads(body)
    assert code == 200
    assert data["curvals"]["video_size"] == "1920x1080"
    assert "torch" in data["avail"]["flashmode"]


def test_torch_and_front_camera(fake_camera: FakeCamera) -> None:
    get(fake_camera, "/enabletorch")
    assert fake_camera.state["torch"] == "on"
    get(fake_camera, "/settings/ffc?set=on")
    assert fake_camera.state["torch"] == "off"
    get(fake_camera, "/enabletorch")
    assert fake_camera.state["torch"] == "off"  # front camera has no flash
    data = json.loads(get(fake_camera, "/status.json?show_avail=1")[1])
    assert data["avail"]["flashmode"] == ["off"]


def test_zoom_is_clamped(fake_camera: FakeCamera) -> None:
    get(fake_camera, "/ptz?zoom=250")
    assert fake_camera.state["zoom"] == "100"


def test_unknown_path_404(fake_camera: FakeCamera) -> None:
    assert get(fake_camera, "/nope")[0] == 404
    assert get(fake_camera, "/settings/unknown?set=1")[0] == 404


def test_sensors_battery(fake_camera: FakeCamera) -> None:
    data = json.loads(get(fake_camera, "/sensors.json")[1])
    assert data["battery_level"]["data"][-1][1][0] == pytest.approx(96.0)


def test_basic_auth() -> None:
    with FakeCamera(username="me", password="pw") as cam:
        assert get(cam, "/status.json")[0] == 401
        assert get(cam, "/status.json", auth=("me", "bad"))[0] == 401
        assert get(cam, "/status.json", auth=("me", "pw"))[0] == 200
