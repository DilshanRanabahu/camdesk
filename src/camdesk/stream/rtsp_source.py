"""PyAV (FFmpeg) based sources: RTSP H.264 (primary). MJPEG builds on the same class."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import av
import numpy as np

from camdesk.core.errors import StreamError
from camdesk.core.frames import SUPPORTED_FORMATS, YUV420P, VideoFrame
from camdesk.stream import hwaccel
from camdesk.stream.source import SourceItem, VideoSource
from camdesk.utils.logging import redact

log = logging.getLogger(__name__)

OPEN_TIMEOUT_S = 6.0
READ_TIMEOUT_S = 3.0  # also bounds how long stop() can take

# "nobuffer" skips FFmpeg's input buffering (lower delay) but drops the one frame read while
# probing the stream — fine for live video, so it's on for the camera and off for files.
LOW_LATENCY_OPTIONS = {
    "fflags": "nobuffer",
    "flags": "low_delay",
    "probesize": "500000",
    "analyzeduration": "500000",
}


# FFmpeg enum values (AVColorRange / AVColorSpace)
_RANGE_JPEG = 2
_SPACE_BT709 = 1
_JPEG_FORMATS = {"yuvj420p": YUV420P}  # same layout as yuv420p, but full range


def frame_from_av(frame: av.VideoFrame, received_at: float) -> VideoFrame:
    """Wrap an av.VideoFrame without copying pixel data when the format is drawable."""
    fmt = frame.format.name
    full_range = int(getattr(frame, "color_range", 0) or 0) == _RANGE_JPEG
    if fmt in _JPEG_FORMATS:  # MJPEG: draw as-is with the full-range shader path
        fmt, full_range = _JPEG_FORMATS[fmt], True
    elif fmt not in SUPPORTED_FORMATS:
        frame = frame.reformat(format=YUV420P)  # rare formats: convert once on the CPU
        fmt = YUV420P
    planes = tuple(
        np.frombuffer(p, dtype=np.uint8).reshape(p.height, p.line_size) for p in frame.planes
    )
    pts_s = float(frame.time) if frame.time is not None else None
    return VideoFrame(
        width=frame.width,
        height=frame.height,
        format=fmt,
        planes=planes,
        pts_s=pts_s,
        received_at=received_at,
        full_range=full_range,
        bt709=int(getattr(frame, "colorspace", 0) or 0) == _SPACE_BT709,
        keepalive=frame,
    )


class PyAvSource(VideoSource):
    """Generic FFmpeg input. Yields raw packets (video + audio) and decoded video frames."""

    transport = "rtsp"

    def __init__(
        self,
        url: str,
        *,
        options: dict[str, str] | None = None,
        container_format: str | None = None,
        use_hwaccel: bool = True,
        yield_packets: bool = True,
        low_latency: bool = True,
    ) -> None:
        self.url = url
        self.options = {**(LOW_LATENCY_OPTIONS if low_latency else {}), **(options or {})}
        self.container_format = container_format
        self.use_hwaccel = use_hwaccel
        self.yield_packets = yield_packets
        self._container: Any = None
        self._device: str | None = None
        self._decoder = ""

    @property
    def decoder(self) -> str:
        return self._decoder

    def open(self) -> None:
        devices = hwaccel.candidates() if self.use_hwaccel else [None]
        last_error: Exception | None = None
        for device in devices:
            try:
                self._container = av.open(
                    self.url,
                    format=self.container_format,
                    options=self.options,
                    timeout=(OPEN_TIMEOUT_S, READ_TIMEOUT_S),
                    hwaccel=hwaccel.make(device),
                )
            except av.error.FFmpegError as exc:
                last_error = exc
                if device is not None and _is_hw_device_error(exc):
                    log.info("%s unavailable (%s); trying next decoder", device, exc)
                    continue
                break
            if not self._container.streams.video:
                self.close()
                raise StreamError("The stream has no video")
            self._device = device
            video = self._container.streams.video[0]
            if device is None:
                video.thread_type = "SLICE"  # frame threading would add frames of delay
            log.info("Opened %s (%s)", redact(self.url), device or "software")
            return
        raise StreamError(_friendly(last_error)) from last_error

    def read(self) -> Iterator[SourceItem]:
        if self._container is None:
            raise StreamError("Source is not open")
        video = self._container.streams.video[0]
        streams = [video, *self._container.streams.audio[:1]]
        try:
            for packet in self._container.demux(streams):
                if packet.size == 0:
                    continue
                if self.yield_packets:
                    yield packet
                if packet.stream is video:
                    yield from self._frames(video, packet.decode())
            # Stream ended normally (files; rare for live): flush frames held by the decoder.
            yield from self._frames(video, video.decode(None))
        except av.error.FFmpegError as exc:
            raise StreamError(_friendly(exc)) from exc
        except OSError as exc:  # socket errors surface as OSError on Windows
            raise StreamError("The connection to the phone was lost") from exc

    def _frames(self, video: Any, decoded: Any) -> Iterator[VideoFrame]:
        for frame in decoded:
            if not self._decoder:
                is_hw = bool(getattr(video.codec_context, "is_hwaccel", False))
                self._decoder = hwaccel.label(self._device, is_hw)
                log.info("Decoding with %s", self._decoder)
            yield frame_from_av(frame, time.perf_counter())

    def close(self) -> None:
        if self._container is not None:
            try:
                self._container.close()
            except Exception:  # closing a broken network stream can raise; nothing to do
                log.debug("Error while closing stream", exc_info=True)
            self._container = None

    @property
    def container(self) -> Any:
        """The open av container (for the recorder to copy stream parameters)."""
        return self._container


class RtspSource(PyAvSource):
    transport = "rtsp"

    def __init__(self, url: str, use_hwaccel: bool = True) -> None:
        super().__init__(url, options={"rtsp_transport": "tcp"}, use_hwaccel=use_hwaccel)


def _is_hw_device_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "hw" in text or "device" in text or "hardware" in text


def _friendly(exc: Exception | None) -> str:
    """Turn FFmpeg errors into short messages for the UI."""
    if exc is None:
        return "Could not open the video stream"
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text:
        return "Wrong username or password"
    if "timed out" in text or "timeout" in text or "etimedout" in text:
        return "The phone did not respond in time"
    # "Immediate exit requested" = our open/read timeout interrupted FFmpeg (no answer).
    if any(k in text for k in ("refused", "no route", "unreachable", "immediate exit")):
        return "Can't reach the phone"
    if "404" in text or "not found" in text:
        return "Video stream not found — is IP Webcam running?"
    if "end of file" in text or "eof" in text:
        return "The video stream ended"
    return "The video stream failed"
