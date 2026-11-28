"""With --debug, a worker thread and the UI thread logging at the same time must not deadlock.

The logging handler lock is held while the TUI sink runs. The sink used to call ``call_from_thread`` (blocks until
the UI thread runs it) while the UI thread, itself logging, waited for the same lock. CI hit it on Windows as an app
frozen right after "Audio start". The scenario runs in a subprocess so a regression is a failure, not a hung run.
"""

import os
import subprocess
import sys
import threading

import pytest

from src import logger

PROBE = "TERMTUBE_DEADLOCK_PROBE"


def _log_500_from_the_worker(done):
    for i in range(500):
        logger.debug("worker %d", i)
    done.set()


async def _pause_until_set(pilot, done):
    """Pause up to ten seconds for ``done``; the caller asserts it."""
    for _ in range(100):
        if done.is_set():
            return
        await pilot.pause(0.1)


@pytest.mark.skipif(os.environ.get(PROBE) != "1", reason="run by the outer test below")
async def test_probe_worker_and_ui_thread_log_concurrently(app, tmp_path, monkeypatch):
    monkeypatch.setattr(logger, "_LOG_DIR", tmp_path / "logs")
    logger.setup(debug=True)
    try:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)  # the main screen has mounted and registered its sink
            done = threading.Event()

            threading.Thread(target=_log_500_from_the_worker, args=(done,), daemon=True).start()
            for i in range(500):  # the UI thread logs in a tight loop, as it does around "Audio start"
                logger.debug("ui %d", i)
            await _pause_until_set(pilot, done)
            assert done.is_set()
            await pilot.pause(0.5)  # let the drain timer write some records into the panel
    finally:
        logger.setup(debug=False)
        logger.register_tui_sink(None)


def test_logging_from_a_worker_and_the_ui_thread_does_not_deadlock():
    probe = f"{__file__}::test_probe_worker_and_ui_thread_log_concurrently"
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", probe]
    env = dict(os.environ, **{PROBE: "1"})
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail("deadlock: the scenario did not finish in 60 s")
    assert result.returncode == 0, result.stdout + result.stderr
