"""scripts/smoke-ipc.py against a real mpv (named pipe or Unix socket, no mocks). Skipped where mpv is absent."""

import subprocess
import sys
from pathlib import Path

import pytest

from src import player

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "smoke-ipc.py"

pytestmark = pytest.mark.skipif(player.mpv_exe(headless=True) is None, reason="mpv is not installed")


def test_real_mpv_answers_polls_pauses_seeks_and_quits():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--require-mpv"], capture_output=True, text=True, timeout=90
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PASS") == 8 and "FAIL" not in result.stdout
