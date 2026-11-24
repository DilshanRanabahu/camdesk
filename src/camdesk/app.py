"""Application entry point: parse arguments, set up logging and settings, start Qt.

This module is the composition root: it is the one place allowed to wire services
(stream/, camera/) to the UI.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections.abc import Sequence
from types import TracebackType

from camdesk import __version__
from camdesk.config import settings as settings_store
from camdesk.core.models import DEFAULT_PORT, CameraProfile
from camdesk.utils.logging import setup_logging

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="camdesk", description="CamDesk IP Webcam controller")
    parser.add_argument("--fake", action="store_true", help="use the built-in fake camera")
    parser.add_argument("--host", help="phone IP address, e.g. 192.168.8.105 (remembered)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="IP Webcam port")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--debug-overlay", action="store_true", help="start with Ctrl+D shown")
    parser.add_argument("--quit-after", type=float, metavar="SECONDS", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _install_excepthooks() -> None:
    """Log unexpected exceptions instead of letting Qt swallow or abort on them."""

    def handle(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            handle(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle
    threading.excepthook = handle_thread


def _set_default_gl_format() -> None:
    """Must run before QApplication: vsync on, no depth buffer (2-D video only)."""
    from PySide6.QtGui import QSurfaceFormat

    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    QSurfaceFormat.setDefaultFormat(fmt)


def _set_windows_app_id() -> None:
    """Give CamDesk its own taskbar identity, so Windows shows our icon instead of Python's."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CamDesk.CamDesk")
    except (AttributeError, OSError):
        log.debug("Could not set the Windows app id", exc_info=True)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = setup_logging(debug=args.debug)
    _install_excepthooks()
    log.info("CamDesk %s starting (log: %s)", __version__, log_file)

    settings = settings_store.load()
    camera = settings.last_camera
    if args.host:
        known = next((c for c in settings.cameras if c.host == args.host), None)
        camera = known or CameraProfile(name=args.host, host=args.host, port=args.port)

    if not args.fake and camera is None:
        # The connect screen arrives in build step 6; until then the IP comes from --host.
        log.error("No camera configured. Run with --host <phone IP> or --fake.")
        sys.stderr.write("No camera yet: run  camdesk --host 192.168.x.x   (or --fake)\n")
        return 2

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from camdesk.camera import endpoints as ep
    from camdesk.camera.client import CameraClient
    from camdesk.config import paths
    from camdesk.core.controller import AppController
    from camdesk.core.frames import LatestFrameBuffer
    from camdesk.core.state import AppState
    from camdesk.stream.mjpeg_source import MjpegSource
    from camdesk.stream.rtsp_source import RtspSource
    from camdesk.stream.service import StreamService
    from camdesk.ui.preview_window import PreviewWindow

    _set_default_gl_format()
    _set_windows_app_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("CamDesk")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(paths.app_icon())))

    buffer = LatestFrameBuffer()  # shared by every stream and the video widget
    fake_camera = None
    if args.fake:
        from camdesk.dev.fake_camera import FakeCamera
        from camdesk.dev.fake_video_source import FakeVideoPlan

        fake_camera = FakeCamera().start()
        plan = FakeVideoPlan(width=1280, height=720)
        camera = CameraProfile(name="Fake camera", host=fake_camera.host, port=fake_camera.port)

        def make_stream(profile: CameraProfile, password: str) -> StreamService:
            return StreamService(buffer, [plan.factory])
    else:

        def make_stream(profile: CameraProfile, password: str) -> StreamService:
            host, port, user = profile.host, profile.port, profile.username
            return StreamService(
                buffer,
                [
                    lambda: RtspSource(ep.rtsp_url(host, port, user, password)),
                    lambda: MjpegSource(ep.mjpeg_url(host, port)),
                ],
            )

    state = AppState()
    client = CameraClient()
    controller = AppController(state, settings, client, make_stream)
    window = PreviewWindow(buffer, state, controller)
    window.show()
    if args.debug_overlay:
        window.debug.toggle()
    assert camera is not None
    controller.connect_camera(camera, remember=not args.fake)
    if args.quit_after:
        QTimer.singleShot(int(args.quit_after * 1000), app.quit)

    try:
        return app.exec()
    finally:
        controller.shutdown()
        if fake_camera is not None:
            fake_camera.stop()
        log.info("CamDesk stopped")
