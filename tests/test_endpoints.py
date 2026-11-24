from __future__ import annotations

from camdesk.camera import endpoints as ep


def test_torch_and_focus_paths() -> None:
    assert ep.torch(True).path == "/enabletorch"
    assert ep.torch(False).path == "/disabletorch"
    assert ep.focus(True).path == "/focus"
    assert ep.focus(False).path == "/nofocus"


def test_settings_commands() -> None:
    cmd = ep.front_camera(True)
    assert cmd.path == "/settings/ffc"
    assert cmd.params == (("set", "on"),)
    assert ep.night_vision(False).params == (("set", "off"),)
    assert ep.video_size("1280x720").params == (("set", "1280x720"),)


def test_values_are_clamped() -> None:
    assert ep.zoom(150).params == (("zoom", "100"),)
    assert ep.zoom(-5).params == (("zoom", "0"),)
    assert ep.quality(0).params == (("set", "1"),)
    assert ep.quality(500).params == (("set", "100"),)


def test_stream_urls() -> None:
    assert ep.rtsp_url("192.168.8.105", 8080) == "rtsp://192.168.8.105:8080/h264_aac.sdp"
    assert ep.mjpeg_url("192.168.8.105", 8080) == "http://192.168.8.105:8080/video"


def test_rtsp_credentials_are_escaped() -> None:
    url = ep.rtsp_url("10.0.0.2", 8080, "me", "p@ss:word")
    assert url == "rtsp://me:p%40ss%3Aword@10.0.0.2:8080/h264_aac.sdp"


def test_mjpeg_credentials() -> None:
    assert ep.mjpeg_url("10.0.0.2", 8080, "me", "p@ss") == "http://me:p%40ss@10.0.0.2:8080/video"
