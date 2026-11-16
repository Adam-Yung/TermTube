"""An exception in the audio launch thread must surface as an error, not leave "Buffering…" on screen forever."""

import asyncio
from unittest.mock import patch

from src import player

ENTRY = {"id": "AAAAAAAAAAA", "title": "t", "_local_path": "/music/a.wav"}


async def test_a_crash_while_launching_is_reported(app, monkeypatch):
    async with app.run_test(size=(100, 30)):
        controller = app.audio
        controller._session = 1
        failures = []
        monkeypatch.setattr(controller, "_launch_failed", lambda session, message: failures.append((session, message)))
        with patch.object(player, "mpv_exe", side_effect=RuntimeError("boom")):
            await asyncio.to_thread(controller._launch_worker, ENTRY, 1, "")
    assert len(failures) == 1 and failures[0][0] == 1 and "Audio failed to start: boom" in failures[0][1]
