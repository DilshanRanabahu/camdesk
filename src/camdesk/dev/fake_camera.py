"""A fake IP Webcam HTTP server, so CamDesk can be developed and tested without the phone.

Mirrors IP Webcam 1.19 on the Samsung Galaxy A06, as checked on the real phone (2026-11-23):
- back camera: torch + autofocus, zoom 1×–10× ("100"…"1000"); front: no torch, fixed focus
- /ptz?zoom=0–100 sets zoom; curvals.zoom reports ratio × 100
- commands reply with XML `<result>Ok</result>`; unknown paths are 404
- sensors.json is `{}` unless sensors are enabled (set `battery` to simulate them)
- `switching=True` simulates the incomplete `avail` sent while changing camera
"""

from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

BACK_FOCUS_MODES = ["off", "auto", "macro", "continuous-video", "continuous-picture"]
FLASH_MODES = ["off", "auto", "on", "red-eye"]  # listed for BOTH cameras on the real phone
VIDEO_SIZES = ["1920x1080", "1280x720", "640x480"]
ZOOM_STEPS = [str(100 + 9 * i) for i in range(101)]  # "100" … "1000"
OK_XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<result>Ok</result>\n'


class FakeCamera:
    """Thread-safe fake IP Webcam. Use as a context manager or call start()/stop()."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        username: str = "",
        password: str = "",
    ) -> None:
        self.username = username
        self.password = password
        self.requests: list[str] = []  # paths received, for tests to inspect
        self.battery: float | None = None  # None = sensors off, like the real phone
        self.charging = True
        self.switching = False
        self.focus_requests = 0
        self._lock = threading.Lock()
        self.state: dict[str, str] = {
            "video_size": "1920x1080",
            "quality": "49",
            "ffc": "off",
            "torch": "off",
            "night_vision": "off",
            "zoom": "100",
            "focusmode": "continuous-video",
            "orientation": "landscape",
        }
        self._server = ThreadingHTTPServer((host, port), self._make_handler())
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self) -> FakeCamera:
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="FakeCamera", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> FakeCamera:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- API behaviour ---------------------------------------------------

    @property
    def front(self) -> bool:
        return self.state["ffc"] == "on"

    def status(self, show_avail: bool) -> dict[str, Any]:
        with self._lock:
            body: dict[str, Any] = {
                "video_connections": 0,
                "audio_connections": 0,
                "curvals": dict(self.state),
            }
        if show_avail:
            avail: dict[str, Any] = {
                "video_size": VIDEO_SIZES[:1] if self.switching else VIDEO_SIZES,
                "orientation": ["landscape", "portrait", "upsidedown", "upsidedown_portrait"],
                "ffc": ["on", "off"],
                "night_vision": ["on", "off"],
            }
            if not self.switching:
                avail |= {
                    "torch": ["off"] if self.front else ["on", "off"],
                    "focusmode": ["off"] if self.front else BACK_FOCUS_MODES,
                    "flashmode": FLASH_MODES,
                    "zoom": ZOOM_STEPS,
                }
            body["avail"] = avail
        return body

    def sensors(self) -> dict[str, Any]:
        if self.battery is None:
            return {}
        now = int(time.time() * 1000)
        return {
            "battery_level": {"unit": "%", "data": [[now, [self.battery]]]},
            "battery_charging": {"unit": "", "data": [[now, [1.0 if self.charging else 0.0]]]},
        }

    def apply(self, path: str, query: dict[str, list[str]]) -> bool:
        """Apply a control command. Returns False for unknown paths."""
        with self._lock:
            if path == "/enabletorch":
                if not self.front:  # front camera has no flash
                    self.state["torch"] = "on"
            elif path == "/disabletorch":
                self.state["torch"] = "off"
            elif path == "/focus":
                self.focus_requests += 1
            elif path == "/nofocus":
                pass
            elif path == "/ptz":
                if "zoom" in query:
                    percent = max(0, min(100, int(query["zoom"][0])))
                    self.state["zoom"] = str(100 + 9 * percent)
            elif path.startswith("/settings/"):
                key = path.removeprefix("/settings/")
                if key not in self.state or "set" not in query:
                    return False
                self.state[key] = query["set"][0]
                if key == "ffc":
                    self.state["torch"] = "off"
                    self.state["zoom"] = "100"
                    self.state["focusmode"] = "off" if self.front else "continuous-video"
            else:
                return False
        return True

    # -- HTTP plumbing ---------------------------------------------------

    def _authorized(self, header: str | None) -> bool:
        if not self.password:
            return True
        expected = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        return header == f"Basic {expected}"

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        camera = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass  # keep test output clean

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                if code == 401:
                    self.send_header("WWW-Authenticate", 'Basic realm="IP Webcam"')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                url = urlparse(self.path)
                camera.requests.append(self.path)
                if not camera._authorized(self.headers.get("Authorization")):
                    self._send(401, b"Unauthorized", "text/plain")
                    return
                query = parse_qs(url.query)
                if url.path == "/status.json":
                    data = camera.status(show_avail="show_avail" in query)
                    self._send(200, json.dumps(data).encode(), "application/json")
                elif url.path == "/sensors.json":
                    self._send(200, json.dumps(camera.sensors()).encode(), "application/json")
                elif camera.apply(url.path, query):
                    self._send(200, OK_XML, "text/xml")
                else:
                    self._send(404, b"Not found", "text/plain")

        return Handler


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with FakeCamera(port=8080) as cam:
        logging.info("Fake IP Webcam running at http://%s  (Ctrl+C to stop)", cam.address)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
