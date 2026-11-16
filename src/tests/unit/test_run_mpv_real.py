"""run_mpv_with_retries with a real subprocess: stderr that is not valid in the locale codec must not break it."""

import sys

from src import player


def run_child(code: str):
    return player.run_mpv_with_retries(
        lambda attempt: [sys.executable, "-c", code],
        headless=True,
        is_stale=lambda: False,
        capture_stderr=True,
        max_attempts=1,
    )


def test_undecodable_stderr_is_replaced_not_raised():
    # 0xC4 0x81 is 'ā' in UTF-8 (undefined byte 0x81 in cp1252); the lone 0x81 is invalid UTF-8.
    outcome = run_child("import sys; sys.stderr.buffer.write(b'caf\\xc3\\xa9 \\xc4\\x81 bad:\\x81'); sys.exit(3)")
    assert outcome.status == "killed" and outcome.returncode == 3
    assert "café ā bad:" in outcome.stderr


def test_exit_codes_still_map_with_stderr_captured():
    assert run_child("import sys; sys.exit(0)").status == "ok"
    assert run_child("import sys; sys.stderr.write('boom'); sys.exit(1)").status == "failed"
