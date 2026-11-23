"""Application entry point: parse arguments, set up logging and settings, start Qt."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections.abc import Sequence
from types import TracebackType

from camdesk import __version__
from camdesk.config import settings as settings_store
from camdesk.utils.logging import setup_logging

log = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="camdesk", description="CamDesk IP Webcam controller")
    parser.add_argument("--fake", action="store_true", help="use the built-in fake camera")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
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


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = setup_logging(debug=args.debug)
    _install_excepthooks()
    log.info("CamDesk %s starting (log: %s)", __version__, log_file)

    settings = settings_store.load()

    fake = None
    if args.fake:
        from camdesk.dev.fake_camera import FakeCamera

        fake = FakeCamera()
        fake.start()
        log.info("Fake camera running at %s", fake.address)

    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication(sys.argv[:1])
    app.setApplicationName("CamDesk")
    app.setApplicationVersion(__version__)

    # Placeholder until the real MainWindow lands (build step 6).
    label = QLabel(f"CamDesk {__version__} — project setup OK")
    label.setMinimumSize(480, 200)
    label.setStyleSheet("background:#0E0F12; color:#E8EAED; font-size:16px; padding:24px;")
    label.setWindowTitle("CamDesk")
    label.show()

    try:
        return app.exec()
    finally:
        settings_store.save(settings)
        if fake is not None:
            fake.stop()
        log.info("CamDesk stopped")
