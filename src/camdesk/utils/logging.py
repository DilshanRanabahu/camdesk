"""Logging setup: rotating file in %APPDATA%\\CamDesk\\logs + console. Credentials are redacted."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from camdesk.config import paths

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(threadName)-12s %(name)s: %(message)s"

# user:password@host inside URLs, and ?password=… / &pass=… query params
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@", re.I)
_QUERY_SECRET = re.compile(r"(?P<key>[?&](?:password|pass|pwd)=)[^&\s]+", re.I)


def redact(text: str) -> str:
    text = _URL_CREDENTIALS.sub(r"\g<scheme>***:***@", text)
    return _QUERY_SECRET.sub(r"\g<key>***", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(debug: bool = False, log_dir: Path | None = None) -> Path:
    """Configure root logging once. Returns the log file path."""
    log_dir = log_dir or paths.logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "camdesk.log"

    formatter = RedactingFormatter(LOG_FORMAT)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.addHandler(file_handler)
    root.addHandler(console)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return log_file
