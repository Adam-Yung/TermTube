"""The --debug log must not carry signed URLs, cookies or tokens, even inside exception text."""

import logging

import pytest

from src import logger


@pytest.mark.parametrize(
    "line, gone",
    [
        ("GET https://rr1.googlevideo.com/videoplayback?expire=1&sig=ABCSECRET&lsig=Z failed", "ABCSECRET"),
        ("extract https://www.youtube.com/watch?v=abc&token=TOPSECRET: error", "TOPSECRET"),
        ("headers Authorization: SAPISIDHASH 123_hash", "123_hash"),
        ("cookie=SID_VALUE; other", "SID_VALUE"),
        ("SAPISID=abcdef", "abcdef"),
    ],
)
def test_redact_removes_the_secret(line, gone):
    out = logger.redact(line)
    assert gone not in out and "<redacted>" in out


def test_redact_keeps_plain_text_and_bounds_length():
    plain = "resolve_stream_url: video_id=abc format=best"
    assert logger.redact(plain) == plain
    assert len(logger.redact("x" * 10000)) < 2100


def test_the_file_handler_redacts_message_and_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "_LOG_DIR", tmp_path)
    logger.setup(debug=True)
    try:
        try:
            raise ValueError("fail https://v.example/p?sig=TRACESECRET")
        except ValueError:
            logger.exception("while loading https://a.example/x?key=MSGSECRET")
        for handler in logging.getLogger("termtube").handlers:
            handler.flush()
        text = logger.log_file().read_text(encoding="utf-8")
    finally:
        logger.setup(debug=False)
    assert "MSGSECRET" not in text and "TRACESECRET" not in text and "while loading" in text
