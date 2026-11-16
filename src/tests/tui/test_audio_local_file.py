"""A Library track is played as a plain file: no stream resolution, no ytdl options (it failed on Windows in CI)."""

import threading
from unittest.mock import patch

from src import player

LOCAL = {"id": "TONE0000001", "title": "Tone", "_local_path": "/music/tone.wav", "_local_type": "audio"}


async def test_a_local_entry_reaches_mpv_as_a_direct_file(app, tmp_path, monkeypatch):
    seen = {}
    done = threading.Event()

    def fake_run(build_cmd, **kwargs):
        seen["cmd"] = build_cmd(1)
        done.set()
        return player.MpvOutcome("killed")

    monkeypatch.setattr("src.history.HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(player, "mpv_exe", lambda headless=False: "mpv")
    async with app.run_test(size=(100, 30)) as pilot:
        with patch.object(player, "run_mpv_with_retries", fake_run), \
                patch("src.streams.resolve_for_playback", side_effect=AssertionError("must not resolve a local file")):
            app.audio.play_audio(LOCAL)
            await pilot.pause(0.5)
            assert done.wait(5)
    cmd = seen["cmd"]
    assert "--no-ytdl" in cmd and cmd[-2:] == ["--", "/music/tone.wav"]
    assert not any(c.startswith("--ytdl-format") for c in cmd)
