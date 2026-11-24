"""Step 8: storage naming, JPEG snapshots, MKV recorder, CaptureManager, and the UI flow."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from camdesk.camera.client import CameraClient
from camdesk.capture import storage
from camdesk.capture.recorder import Recorder
from camdesk.capture.snapshot import encode_jpeg, save_snapshot
from camdesk.config.settings import Settings
from camdesk.core.controller import AppController
from camdesk.core.frames import NV12, YUV420P, LatestFrameBuffer, VideoFrame
from camdesk.core.models import CameraProfile, ConnectionState, ToastLevel
from camdesk.core.state import AppState
from camdesk.dev.fake_camera import FakeCamera
from camdesk.dev.fake_video_source import test_pattern as color_bars
from camdesk.stream.rtsp_source import PyAvSource
from camdesk.stream.service import StreamService
from camdesk.ui.main_window import MainWindow
from qt_helpers import SignalRecorder, wait_until
from test_controller import FakeSecrets

# -- test media: like the phone (keyframe every 0.5 s, video + AAC audio) ----------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("media") / "phone_like.mkv"
    with av.open(str(path), "w") as box:
        v = box.add_stream("mpeg4", rate=30)
        v.width, v.height, v.pix_fmt = 320, 240, "yuv420p"
        v.codec_context.gop_size = 15
        a = box.add_stream("aac", rate=44100)
        a.layout = "mono"
        for i in range(120):  # 4 s
            img = np.full((240, 320, 3), (i * 2) % 255, np.uint8)
            frame = av.VideoFrame.from_ndarray(img, format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 30)
            box.mux(v.encode(frame))
        for n in range(4 * 44100 // 1024):
            af = av.AudioFrame.from_ndarray(
                np.zeros((1, 1024), np.float32), format="fltp", layout="mono"
            )
            af.sample_rate, af.pts = 44100, n * 1024
            box.mux(a.encode(af))
        box.mux(a.encode(None))
        box.mux(v.encode(None))
    return path


def mkv_info(path: Path) -> dict:
    with av.open(str(path)) as box:
        types = [s.type for s in box.streams]
        video = box.streams.video[0]
        packets = [p for p in box.demux(video) if p.size]
        decoded = sum(len(p.decode()) for p in packets)
    return {"types": types, "packets": len(packets), "decoded": decoded,
            "first_key": packets[0].is_keyframe, "first_pts": packets[0].pts}  # fmt: skip


class PacedFile(PyAvSource):
    """A file played like a live camera: real-time pace, loops forever, transport "rtsp"."""

    transport = "rtsp"

    def __init__(self, path: Path) -> None:
        super().__init__(str(path), use_hwaccel=False, low_latency=False)

    def read(self):  # type: ignore[override]
        while True:
            for item in super().read():
                yield item
                if isinstance(item, VideoFrame):
                    time.sleep(1 / 30)
            self.close()
            self.open()


def feed(recorder: Recorder, media: Path, loops: int = 1) -> None:
    for _ in range(loops):
        source = PyAvSource(str(media), use_hwaccel=False, low_latency=False)
        source.open()
        for item in source.read():
            if not isinstance(item, VideoFrame):
                recorder.push(item)
        source.close()


# -- storage ------------------------------------------------------------------------


def test_names_and_parts(tmp_path: Path) -> None:
    now = datetime(2026, 11, 24, 21, 4, 5)
    first = storage.snapshot_path(tmp_path, now)
    assert first.name == "snapshot_2026-11-24_21-04-05.jpg"
    first.write_bytes(b"x")
    assert storage.snapshot_path(tmp_path, now).name == "snapshot_2026-11-24_21-04-05_2.jpg"
    base = storage.recording_base(tmp_path / "rec", now)
    assert storage.part_path(base, 1).name == "recording_2026-11-24_21-04-05.mkv"
    assert storage.part_path(base, 3).name == "recording_2026-11-24_21-04-05_part3.mkv"
    assert storage.free_bytes(tmp_path / "does" / "not" / "exist") is not None


# -- snapshots ---------------------------------------------------------------------


def _frames() -> list[VideoFrame]:
    y, u, v = color_bars(640, 360)
    uv = np.empty((180, 640), np.uint8)
    uv[:, 0::2], uv[:, 1::2] = u, v
    padded = np.zeros((360, 704), np.uint8)
    padded[:, :640] = y  # row padding, like decoder output
    return [
        VideoFrame(width=640, height=360, format=YUV420P, planes=(y, u, v)),
        VideoFrame(width=640, height=360, format=NV12, planes=(padded, uv)),
    ]


@pytest.mark.parametrize("frame", _frames(), ids=["yuv420p", "nv12-padded"])
def test_snapshot_jpeg_colors(frame: VideoFrame, tmp_path: Path) -> None:
    path = save_snapshot(frame, tmp_path)
    assert path.suffix == ".jpg" and not list(tmp_path.glob("*.part"))
    with av.open(str(path)) as box:
        img = next(box.decode(video=0)).to_ndarray(format="rgb24")
    assert img.shape == (360, 640, 3)
    assert np.allclose(img[100, 500], [191, 0, 0], atol=6)  # 75% red bar
    assert np.allclose(img[100, 20], [191, 191, 191], atol=6)  # 75% white bar


def test_jpeg_is_small_but_real() -> None:
    data = encode_jpeg(_frames()[0])
    assert data[:2] == b"\xff\xd8" and 2_000 < len(data) < 200_000


# -- recorder ----------------------------------------------------------------------


def test_records_playable_mkv_with_audio(qapp: QApplication, media: Path, tmp_path: Path) -> None:
    rec = Recorder()
    stopped = SignalRecorder(rec.stopped)
    first = rec.start(tmp_path, segment_s=999)
    feed(rec, media)
    rec.stop()
    assert wait_until(lambda: stopped.count == 1) and stopped[0][0] == ""
    info = mkv_info(first)
    assert info["types"] == ["video", "audio"]
    assert info["first_key"] and info["first_pts"] == 0
    assert info["decoded"] == info["packets"] >= 110


def test_segments_start_on_keyframes(qapp: QApplication, media: Path, tmp_path: Path) -> None:
    rec = Recorder()
    parts = SignalRecorder(rec.part_started)
    rec.start(tmp_path, segment_s=1.5)
    feed(rec, media)
    rec.stop()
    files = sorted(tmp_path.glob("recording_*.mkv"))
    assert len(files) == 3
    assert wait_until(lambda: parts.count == 3)
    for f in files:
        info = mkv_info(f)
        assert info["first_key"] and info["first_pts"] == 0 and info["decoded"] == info["packets"]


def test_new_stream_starts_new_part(qapp: QApplication, media: Path, tmp_path: Path) -> None:
    rec = Recorder()
    rec.start(tmp_path, segment_s=999)
    feed(rec, media, loops=2)  # two separate containers = like a reconnect
    rec.stop()
    assert len(list(tmp_path.glob("recording_*.mkv"))) == 2


def test_stop_without_waiting_and_busy_guard(
    qapp: QApplication, media: Path, tmp_path: Path
) -> None:
    rec = Recorder()
    stopped = SignalRecorder(rec.stopped)
    rec.start(tmp_path, segment_s=999)
    feed(rec, media)
    t = time.perf_counter()
    rec.stop(timeout_s=0)
    assert time.perf_counter() - t < 0.2  # never blocks the UI thread
    assert not rec.active
    with pytest.raises(RuntimeError):
        if rec.busy:
            rec.start(tmp_path, 999)
        else:
            raise RuntimeError("already finished — fine")
    assert wait_until(lambda: stopped.count == 1)
    assert not rec.busy


def test_packets_ignored_when_not_recording(media: Path, tmp_path: Path) -> None:
    rec = Recorder()
    feed(rec, media)  # nothing started
    assert list(tmp_path.glob("*.mkv")) == []


# -- capture manager + UI ------------------------------------------------------------


@pytest.fixture
def window(qapp: QApplication, fake_camera: FakeCamera, media: Path) -> Iterator[MainWindow]:
    buffer = LatestFrameBuffer()
    state = AppState()

    def make_stream(profile: CameraProfile, password: str) -> StreamService:
        # A file source yields real packets and reports transport "rtsp", like the phone.
        return StreamService(buffer, [lambda: PacedFile(media)], backoff_s=(0.01,))

    controller = AppController(
        state,
        Settings(),
        CameraClient(),
        make_stream,
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
        assert wait_until(lambda: state.stream_info.transport == "rtsp")
        yield win
        win.close()
    finally:
        controller.shutdown()


def test_space_takes_snapshot(window: MainWindow) -> None:
    toasts = SignalRecorder(window.state.notification)
    QTest.keyClick(window, Qt.Key.Key_Space)
    assert wait_until(lambda: any(t[0].level is ToastLevel.SUCCESS for t in toasts.calls))
    files = list(window.controller.settings.snapshots_path().glob("snapshot_*.jpg"))
    assert len(files) == 1


def test_record_toggle_badge_and_file(window: MainWindow) -> None:
    QTest.keyClick(window, Qt.Key.Key_R)
    assert window.state.recording.active
    assert window.rec_badge.isVisible() and "REC" in window.rec_badge.text()
    assert window.dock.record.property("recording") == "true"
    assert wait_until(lambda: window.state.recording.elapsed_s >= 1.0, 4000)
    toasts = SignalRecorder(window.state.notification)
    QTest.keyClick(window, Qt.Key.Key_R)  # stop: returns at once, file finishes in the background
    assert wait_until(lambda: not window.state.recording.active)
    assert window.rec_badge.isHidden()
    assert wait_until(lambda: any("Recording saved" in t[0].message for t in toasts.calls))
    files = list(window.controller.settings.recordings_path().glob("recording_*.mkv"))
    assert files and mkv_info(files[0])["first_key"]


def test_disconnect_finishes_recording(window: MainWindow) -> None:
    window.controller.capture.start_recording()
    assert window.state.recording.active
    window.controller.disconnect()
    assert wait_until(lambda: not window.state.recording.active)


def test_recording_refused_on_mjpeg(window: MainWindow) -> None:
    from camdesk.core.models import StreamInfo

    window.state.set_stream_info(StreamInfo(width=640, height=360, transport="mjpeg"))
    toasts = SignalRecorder(window.state.notification)
    window.controller.capture.start_recording()
    assert not window.state.recording.active
    assert toasts.count == 1 and "main video stream" in toasts[0][0].message
