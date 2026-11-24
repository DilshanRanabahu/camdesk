"""PyAV source tests using a small local video file (no phone or network)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from camdesk.core.errors import StreamError
from camdesk.core.frames import NV12, YUV420P, VideoFrame
from camdesk.stream import hwaccel
from camdesk.stream.rtsp_source import PyAvSource, _friendly, frame_from_av


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """1 s of 320x240 video (MPEG-4) + AAC audio in MKV — same layout as the phone stream."""
    path = tmp_path_factory.mktemp("media") / "sample.mkv"
    with av.open(str(path), "w") as box:
        video = box.add_stream("mpeg4", rate=30)
        video.width, video.height, video.pix_fmt = 320, 240, "yuv420p"
        audio = box.add_stream("aac", rate=44100)
        audio.layout = "mono"
        for i in range(30):
            img = np.full((240, 320, 3), i * 8, np.uint8)
            frame = av.VideoFrame.from_ndarray(img, format="rgb24")
            frame.pts = i
            frame.time_base = Fraction(1, 30)
            box.mux(video.encode(frame))
        for n in range(10):  # AAC encodes 1024-sample frames
            samples = av.AudioFrame.from_ndarray(
                np.zeros((1, 1024), np.float32), format="fltp", layout="mono"
            )
            samples.sample_rate = 44100
            samples.pts = n * 1024
            box.mux(audio.encode(samples))
        box.mux(audio.encode(None))
        box.mux(video.encode(None))
    return path


def test_reads_frames_and_packets(sample_video: Path) -> None:
    source = PyAvSource(str(sample_video), use_hwaccel=False, low_latency=False)
    source.open()
    frames = []
    packet_types = set()
    for item in source.read():
        if isinstance(item, VideoFrame):
            frames.append(item)
        else:
            packet_types.add(item.stream.type)  # read while the container is open
    source.close()
    assert len(frames) == 30
    assert frames[0].width == 320 and frames[0].format == YUV420P
    assert packet_types == {"video", "audio"}
    assert source.decoder == "Software (CPU)"


def test_packets_can_be_disabled(sample_video: Path) -> None:
    source = PyAvSource(
        str(sample_video), use_hwaccel=False, low_latency=False, yield_packets=False
    )
    source.open()
    items = list(source.read())
    source.close()
    assert items and all(isinstance(i, VideoFrame) for i in items)


def test_hwaccel_open_on_this_machine(sample_video: Path) -> None:
    """Uses the GPU when available; must still decode correctly either way."""
    source = PyAvSource(str(sample_video), low_latency=False)
    source.open()
    frames = [i for i in source.read() if isinstance(i, VideoFrame)]
    source.close()
    assert len(frames) == 30
    assert source.decoder  # some label was set


def test_low_latency_drops_at_most_the_probe_frame(sample_video: Path) -> None:
    source = PyAvSource(str(sample_video), use_hwaccel=False)  # live-camera options
    source.open()
    frames = [i for i in source.read() if isinstance(i, VideoFrame)]
    source.close()
    assert len(frames) >= 29


def test_missing_file_raises_stream_error(tmp_path: Path) -> None:
    source = PyAvSource(str(tmp_path / "nope.mkv"), use_hwaccel=False, low_latency=False)
    with pytest.raises(StreamError):
        source.open()


def test_close_is_idempotent(sample_video: Path) -> None:
    source = PyAvSource(str(sample_video), use_hwaccel=False, low_latency=False)
    source.open()
    source.close()
    source.close()


@pytest.mark.parametrize("fmt", ["nv12", "yuv420p", "yuvj420p"])
def test_frame_from_av_formats(fmt: str) -> None:
    src = av.VideoFrame(64, 48, fmt)
    frame = frame_from_av(src, received_at=1.5)
    assert frame.format in (NV12, YUV420P)
    assert frame.received_at == 1.5
    assert frame.plane_view(0).shape == (48, 64)
    assert len(frame.planes) == (2 if frame.format == NV12 else 3)


def test_hwaccel_candidates_end_with_software() -> None:
    options = hwaccel.candidates()
    assert options[-1] is None
    assert "cuda" not in options  # fails on the phone's stream
    assert hwaccel.label("d3d11va", True) == "D3D11VA (GPU)"
    assert hwaccel.label("d3d11va", False) == "Software (CPU)"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Server returned 401 Unauthorized", "Wrong username or password"),
        ("Connection timed out", "The phone did not respond in time"),
        ("Connection refused", "Can't reach the phone"),
        ("[Errno 1414092869] Immediate exit requested: 'rtsp://x'", "Can't reach the phone"),
        ("Server returned 404 Not Found", "Video stream not found — is IP Webcam running?"),
        ("something odd", "The video stream failed"),
    ],
)
def test_friendly_errors(text: str, expected: str) -> None:
    assert _friendly(Exception(text)) == expected
