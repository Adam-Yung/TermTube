"""scripts/e2e-local.py: the real app in a real pseudo-terminal with a real mpv. Skipped where mpv is absent.

CI runs the same script against the installed copy on every platform (docs/guides/ci.md); this covers a dev machine.
Windows is left to CI: it needs pywinpty.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from src import player

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "e2e-local.py"

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="needs pywinpty; run by CI"),
    pytest.mark.skipif(player.mpv_exe(headless=True) is None, reason="mpv is not installed"),
]


def test_the_real_app_plays_pauses_seeks_stops_and_quits():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout and result.stdout.count("PASS") == 14
