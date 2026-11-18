"""A save that fails (read-only dir, disk full) tells the user instead of crashing the screen."""

import threading

import pytest

from src import playlist, store


def full(path, payload):
    raise OSError(28, "No space left on device")


@pytest.mark.parametrize("from_thread", [False, True])
async def test_a_failed_playlist_save_is_a_notice_and_the_playlist_stays(app, temp_playlists, monkeypatch, from_thread):
    monkeypatch.setattr(store, "atomic_write", full)
    told = []
    async with app.run_test(size=(100, 30)) as pilot:
        monkeypatch.setattr(type(app), "notify", lambda self, msg, **kw: told.append(msg))
        if from_thread:
            worker = threading.Thread(target=lambda: playlist.create("Mix"))
            worker.start()
            while worker.is_alive():
                await pilot.pause()
            worker.join()
        else:
            playlist.create("Mix")
        await pilot.pause()
        assert playlist.list_playlists()[0]["name"] == "Mix"
    assert len(told) == 1 and "No space left" in told[0]
