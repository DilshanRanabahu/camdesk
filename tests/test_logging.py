from __future__ import annotations

import logging
from pathlib import Path

from camdesk.utils.logging import redact, setup_logging


def test_redacts_url_credentials() -> None:
    assert redact("rtsp://admin:s3cret@192.168.8.105:8080/h264_aac.sdp") == (
        "rtsp://***:***@192.168.8.105:8080/h264_aac.sdp"
    )


def test_redacts_password_query() -> None:
    assert redact("GET /login?user=a&password=abc&x=1") == "GET /login?user=a&password=***&x=1"


def test_plain_urls_untouched() -> None:
    url = "http://192.168.8.105:8080/status.json?show_avail=1"
    assert redact(url) == url


def test_log_file_is_redacted(tmp_path: Path) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    try:
        log_file = setup_logging(log_dir=tmp_path)
        logging.getLogger("test").info("opening http://me:pw@1.2.3.4/video")
        for handler in root.handlers:
            handler.close()
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
    text = log_file.read_text(encoding="utf-8")
    assert "me:pw" not in text
    assert "***:***@1.2.3.4" in text
