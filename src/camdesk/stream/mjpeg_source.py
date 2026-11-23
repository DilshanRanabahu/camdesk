"""MJPEG fallback (http://<ip>:8080/video), decoded by FFmpeg's MJPEG decoder.

Used only when RTSP fails. No audio and no packets for the recorder.
"""

from __future__ import annotations

from camdesk.stream.rtsp_source import PyAvSource


class MjpegSource(PyAvSource):
    transport = "mjpeg"

    def __init__(self, url: str) -> None:
        super().__init__(
            url,
            container_format="mpjpeg",  # multipart/x-mixed-replace JPEG stream
            use_hwaccel=False,  # JPEG decode is cheap; no GPU path needed
            yield_packets=False,
        )
