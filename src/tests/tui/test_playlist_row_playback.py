"""``v`` ``a`` ``e`` on a playlist row play or queue it from the list; a video run steps with the player's result."""

import threading
from functools import partial
from unittest.mock import MagicMock

import pytest

from src import innertube, player, playlist
from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tui.audio_controller import AudioController
from src.tui.screens.mixins.library_rail import PLAYLIST_VIEW
from src.tui.screens.watch_modal import WatchModal

ROW = {"id": "PLhits", "title": "Hits", "_is_playlist": True, "_type": "playlist", "thumbnail": "u"}


def vids(n, start=0):
    return [{"id": f"v{i:010d}", "title": f"Song {i}"} for i in range(start, start + n)]


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    monkeypatch.setattr(WatchModal, "on_mount", lambda self: None)


def serve(monkeypatch, *pages):
    queue = list(pages)
    monkeypatch.setattr(innertube, "fetch_playlist_page", lambda pid, token="", **_: queue.pop(0))


async def settle(app, pilot):
    for _ in range(3):
        await app.workers.wait_for_complete()
        await pilot.pause(0.1)


async def on_row(app, pilot, row=ROW):
    await pilot.pause(0.8)
    screen = app.screen
    screen._selected_entry = lambda: row
    return screen


def ids(entries):
    return [e["id"] for e in entries]


async def test_a_plays_every_page_of_the_playlist_as_audio(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2), "T"), innertube.ChannelPage(vids(2, 1), ""))
    async with app.run_test(size=(120, 40)) as pilot:
        await on_row(app, pilot)
        await pilot.press("a")
        await settle(app, pilot)
        assert app.audio.entry["id"] == "v0000000000"
        assert ids(app.audio.queue) == ["v0000000001", "v0000000002"]


async def test_e_queues_the_playlist_behind_the_playing_track(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2), ""))
    async with app.run_test(size=(120, 40)) as pilot:
        await on_row(app, pilot)
        app.audio.play_audio({"id": "other000000", "title": "x"})
        await pilot.press("e")
        await settle(app, pilot)
        assert app.audio.entry["id"] == "other000000" and len(app.audio.queue) == 2


def _gated_page(release, pid, token="", **_):
    release.wait(5)
    return innertube.ChannelPage(vids(2), "")


async def test_a_result_that_arrives_after_x_is_dropped(app, monkeypatch):
    release = threading.Event()

    monkeypatch.setattr(innertube, "fetch_playlist_page", partial(_gated_page, release))
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        screen.action_audio()
        app.audio.stop_audio()
        release.set()
        await settle(app, pilot)
        assert not app.audio.is_playing


async def test_an_unavailable_playlist_says_youtubes_reason(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage([], "", {"unavailable": "The playlist does not exist."}))
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        screen._hint = MagicMock()
        screen.action_audio()
        await settle(app, pilot)
        assert screen._hint.call_args.args[0] == "The playlist does not exist."


async def test_v_runs_the_playlist_following_the_player_results(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(3), ""))
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        await pilot.press("v")
        await settle(app, pilot)
        seen = []
        for result in ("ended", "next", "prev", "failed", "ended"):
            assert isinstance(app.screen, WatchModal)
            seen.append(app.screen._position[0])
            app.screen.dismiss(result)
            await pilot.pause(0.1)
        assert seen == [1, 2, 3, 2, 3]
        assert app.screen is screen


async def test_stopping_ends_the_run_and_so_do_three_failures(app, monkeypatch):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        screen._watch_run(vids(9), 0)
        await pilot.pause(0.1)
        app.screen.dismiss("stopped")
        await pilot.pause(0.1)
        assert app.screen is screen
        screen._watch_run(vids(9), 0)
        for _ in range(3):
            await pilot.pause(0.1)
            app.screen.dismiss("failed")
        await pilot.pause(0.1)
        assert app.screen is screen


async def test_the_player_keys_step_only_inside_a_run(app):
    async with app.run_test(size=(120, 40)) as pilot:
        results = []
        for key in (">", "<"):
            app.push_screen(WatchModal(vids(1)[0], position=(1, 2)), results.append)
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
        app.push_screen(WatchModal(vids(1)[0]), results.append)
        await pilot.pause()
        await pilot.press(">")
        await pilot.pause()
        assert results == ["next", "prev"] and isinstance(app.screen, WatchModal)


async def test_v_on_a_row_is_refused_while_audio_plays(app, monkeypatch):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        app.audio._play_pending = True
        screen.action_watch()
        await settle(app, pilot)
        assert app.screen is screen


async def test_the_panel_lists_the_playback_keys_for_a_playlist_row(app):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await on_row(app, pilot)
        assert {"v", "a", "e"} <= {key for key, _ in screen.panel_hints()}


async def test_a_on_a_rail_playlist_plays_it(app, monkeypatch, tmp_path):
    monkeypatch.setattr(playlist, "_PLAYLISTS_PATH", tmp_path / "playlists.json")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.8)
        screen = app.screen
        record = playlist.create("Local", vids(2))
        await pilot.press("f5")
        await pilot.pause(0.5)
        screen._select_collection(PLAYLIST_VIEW + record["id"])
        await pilot.pause(0.5)
        await pilot.press("tab")
        await pilot.pause(0.2)
        assert screen._rail_focused()
        await pilot.press("a")
        await settle(app, pilot)
        assert app.audio.entry["id"] == "v0000000000" and len(app.audio.queue) == 1


@pytest.mark.parametrize("code,result", [(0, "ended"), (4, "stopped"), (10, "next"), (11, "prev"), (12, "stopped")])
def test_the_exit_code_says_what_the_mpv_window_asked_for(code, result):
    modal = WatchModal(vids(1)[0], position=(1, 2))
    modal._cleanup_ipc = lambda path: None
    modal._dismiss_from_thread = MagicMock()
    modal._finish(player.MpvOutcome("ok", code), "conf", "")
    modal._dismiss_from_thread.assert_called_once_with(result)


def test_only_a_run_binds_the_stepping_keys_in_mpv():
    plain, run = player.write_input_conf(), player.write_input_conf(sequence=True)
    with open(plain, encoding="utf-8") as a, open(run, encoding="utf-8") as b:
        assert "CLOSE_WIN" not in a.read()
        text = b.read()
    assert "> quit 10" in text and "< quit 11" in text and "CLOSE_WIN quit 12" in text


def test_each_item_of_a_run_has_its_own_ipc_socket():
    first, second = (WatchModal(vids(1)[0], position=(n, 2)) for n in (1, 2))
    assert first._socket != second._socket
