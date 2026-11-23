from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication

from camdesk.core.frames import LatestFrameBuffer
from camdesk.core.models import ConnectionState
from camdesk.dev.fake_video_source import FakeVideoPlan
from camdesk.stream.service import StreamService
from qt_helpers import SignalRecorder

FAST_BACKOFF = (0.01, 0.02)


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def wait_for_state(states: SignalRecorder, wanted: ConnectionState, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not any(args[0] is wanted for args in states.calls):
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"never reached {wanted}; got {[a[0] for a in states.calls]}"
        states.wait(int(remaining * 1000))


@pytest.fixture
def make_service(qapp: QCoreApplication) -> Iterator:
    services: list[StreamService] = []

    def make(*plans: FakeVideoPlan, **kwargs: object) -> StreamService:
        kwargs.setdefault("backoff_s", FAST_BACKOFF)
        svc = StreamService(LatestFrameBuffer(), [p.factory for p in plans], **kwargs)
        services.append(svc)
        return svc

    yield make
    for svc in services:
        svc.stop()


def test_connects_and_delivers_frames(make_service) -> None:
    svc = make_service(FakeVideoPlan(fps=60))
    states = SignalRecorder(svc.state_changed)
    ready = SignalRecorder(svc.frame_ready)
    info = SignalRecorder(svc.stream_info_changed)
    svc.start()
    wait_for_state(states, ConnectionState.CONNECTED)
    assert states[0][0] is ConnectionState.CONNECTING
    assert ready.wait(2000) or ready.count > 0
    frame = svc.buffer.take()
    assert frame is not None and (frame.width, frame.height) == (640, 360)
    assert info.wait(3000)
    stream_info = info[0][0]
    assert stream_info.transport == "fake" and stream_info.decoder == "Test pattern"


def test_frame_ready_is_coalesced(make_service) -> None:
    svc = make_service(FakeVideoPlan(fps=200))
    ready = SignalRecorder(svc.frame_ready)
    svc.start()
    assert ready.wait(2000)
    time.sleep(0.3)  # producer keeps going while nobody takes frames
    QCoreApplication.processEvents()
    assert ready.count == 1  # one signal until the consumer takes the frame
    assert svc.buffer.dropped > 10


def test_reconnects_after_drop(make_service) -> None:
    plan = FakeVideoPlan(fps=200, frames_per_open=5)
    svc = make_service(plan)
    states = SignalRecorder(svc.state_changed)
    svc.start()
    wait_for_state(states, ConnectionState.RECONNECTING)
    deadline = time.monotonic() + 3
    while plan.opens < 3 and time.monotonic() < deadline:
        states.wait(200)
    assert plan.opens >= 3
    connected = [a for a in states.calls if a[0] is ConnectionState.CONNECTED]
    assert len(connected) >= 2  # came back after each drop


def test_fails_after_max_attempts_then_retry(make_service) -> None:
    plan = FakeVideoPlan(fail_opens=3)
    svc = make_service(plan, max_failures=3)
    states = SignalRecorder(svc.state_changed)
    svc.start()
    wait_for_state(states, ConnectionState.FAILED)
    failed = next(a for a in states.calls if a[0] is ConnectionState.FAILED)
    assert "reach" in failed[1]
    assert plan.opens == 3
    svc.retry()  # 4th open succeeds
    wait_for_state(states, ConnectionState.CONNECTED)


def test_falls_back_to_second_source(make_service) -> None:
    broken = FakeVideoPlan(fail_opens=100)
    backup = FakeVideoPlan(width=320, height=180)
    svc = make_service(broken, backup, max_failures=10)
    states = SignalRecorder(svc.state_changed)
    svc.start()
    wait_for_state(states, ConnectionState.CONNECTED)
    assert broken.opens == 2 and backup.opens == 1
    deadline = time.monotonic() + 2
    frame = None
    while frame is None and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        frame = svc.buffer.take()
    assert frame is not None and frame.width == 320


def test_packets_reach_sinks_and_stop_is_fast(make_service) -> None:
    class PacketPlan(FakeVideoPlan):
        def factory(self):  # type: ignore[override]
            source = super().factory()
            original = source.read

            def read():
                for frame in original():
                    yield b"packet"  # anything that isn't a VideoFrame is a packet
                    yield frame

            source.read = read  # type: ignore[method-assign]
            return source

    svc = make_service(PacketPlan(fps=100))
    got: list[object] = []
    svc.add_packet_sink(got.append)
    states = SignalRecorder(svc.state_changed)
    svc.start()
    wait_for_state(states, ConnectionState.CONNECTED)
    time.sleep(0.1)
    started = time.perf_counter()
    svc.stop()
    assert time.perf_counter() - started < 1.0
    assert got and got[0] == b"packet"
    assert svc.state is ConnectionState.IDLE
    assert svc.buffer.peek() is None


def test_bad_sink_is_removed(make_service) -> None:
    svc = make_service(FakeVideoPlan(fps=100))

    def broken_sink(_packet: object) -> None:
        raise RuntimeError("boom")

    svc.add_packet_sink(broken_sink)
    svc._feed_sinks(b"x")
    assert broken_sink not in svc._sinks
