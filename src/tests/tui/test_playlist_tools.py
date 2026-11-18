"""Playlists tab: new, rename, delete, open, remove items, reorder, play-all, modal multi-select."""

from unittest.mock import patch

import pytest
from textual.widgets import Input

from src import playlist
from src.tui.screens.name_modal import NameModal
from src.tui.screens.playlist_modal import PlaylistModal
from src.tui.widgets.video_list import VideoListPanel


@pytest.fixture(autouse=True)
def no_detail_network(monkeypatch, temp_playlists):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)


def vids(*names):
    return [{"id": f"vid{n:08d}", "title": f"Clip {n}", "uploader": "Chan"} for n in names]


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def row_ids(app):
    return panel_of(app).visible_ids()


def item_ids(pid):
    return [i["id"] for i in playlist.get(pid)["items"]]


async def open_tab(app, pilot):
    await pilot.pause(0.8)
    await pilot.press("f6")
    await pilot.pause(0.5)


async def name_it(app, pilot, name):
    assert isinstance(app.screen, NameModal)
    app.screen.query_one("#name-input", Input).value = name
    await app.screen.query_one("#name-input", Input).action_submit()
    await pilot.pause(0.3)


async def test_n_creates_a_playlist_and_a_duplicate_is_refused(app):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("n")
        await pilot.pause(0.2)
        await name_it(app, pilot, "Road trip")
        assert [p["name"] for p in playlist.list_playlists()] == ["Road trip"]
        assert row_ids(app) == [f"__playlist__{playlist.list_playlists()[0]['id']}"]
        await pilot.press("n")
        await pilot.pause(0.2)
        await name_it(app, pilot, "road TRIP")
        assert len(playlist.list_playlists()) == 1


async def test_n_outside_the_playlists_tab_only_hints(app):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.8)
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("n")
            await pilot.pause(0.2)
        assert not isinstance(app.screen, NameModal) and "Playlists tab" in notify.call_args.args[0]


async def test_rename_from_the_index_and_from_inside(app):
    pid = playlist.create("Old", vids(1))["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("R")
        await pilot.pause(0.2)
        await name_it(app, pilot, "Newer")
        assert playlist.get(pid)["name"] == "Newer"
        await pilot.press("enter")
        await pilot.pause(0.4)
        await pilot.press("R")
        await pilot.pause(0.2)
        await name_it(app, pilot, "Newest")
        assert playlist.get(pid)["name"] == "Newest" and app.screen._current_tab == f"playlist:{pid}"


async def test_delete_playlist_asks_keeps_videos_and_undo_restores(app):
    pid = playlist.create("Doomed", vids(1, 2))["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("D", "n")
        await pilot.pause(0.2)
        assert playlist.get(pid) is not None
        await pilot.press("D", "y")
        await pilot.pause(0.3)
        assert playlist.get(pid) is None
        await pilot.press("u")
        await pilot.pause(0.3)
        assert item_ids(pid) == [v["id"] for v in vids(1, 2)]


async def test_open_playlist_shows_titles_never_bare_ids_and_filters(app):
    pid = playlist.create("P", vids(*range(1, 26)))["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await pilot.pause(0.4)
        panel = panel_of(app)
        assert app.screen._current_tab == f"playlist:{pid}" and len(row_ids(app)) == 25
        assert panel.selected_entry["title"] == "Clip 1"
        await pilot.press("l")  # paging works
        await pilot.pause(0.2)
        assert panel.current_page == 2
        await pilot.press("f", "2", "5", "enter")
        await pilot.pause(0.3)
        assert row_ids(app) == [vids(25)[0]["id"]]


async def test_migrated_item_without_title_is_filled_from_the_cache(app):
    pid = playlist.create("P", [{"id": "abc123def45"}])["id"]
    app.cache.pin_video("abc123def45", {"id": "abc123def45", "title": "From cache"})
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await pilot.pause(0.4)
        assert panel_of(app).selected_entry["title"] == "From cache"
        assert playlist.get(pid)["items"][0]["title"] == "From cache"


async def test_D_inside_removes_marked_items_and_u_restores_in_place(app):
    pid = playlist.create("P", vids(1, 2, 3, 4))["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await pilot.pause(0.4)
        await pilot.press("m", "j", "m", "D", "y")  # marks 1 and 3 (m moves down)
        await pilot.pause(0.3)
        assert item_ids(pid) == [v["id"] for v in vids(2, 4)]
        await pilot.press("u")
        await pilot.pause(0.3)
        assert item_ids(pid) == [v["id"] for v in vids(1, 2, 3, 4)]


async def test_J_and_K_move_the_item_and_stop_at_the_ends(app):
    pid = playlist.create("P", vids(1, 2, 3))["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        await pilot.press("enter")
        await pilot.pause(0.4)
        await pilot.press("K")  # first row: nowhere to go
        await pilot.pause(0.1)
        assert item_ids(pid) == [v["id"] for v in vids(1, 2, 3)]
        await pilot.press("J", "J", "J")
        await pilot.pause(0.3)
        assert item_ids(pid) == [v["id"] for v in vids(2, 3, 1)]
        assert panel_of(app).selected_entry["id"] == vids(1)[0]["id"]
        await pilot.press("K")
        await pilot.pause(0.2)
        assert item_ids(pid) == [v["id"] for v in vids(2, 1, 3)]


async def test_play_shuffle_and_enqueue_all_use_the_audio_controller(app):
    playlist.create("P", vids(1, 2, 3))
    async with app.run_test(size=(110, 40)) as pilot:
        await open_tab(app, pilot)
        many = patch.object(app.audio, "enqueue_many", return_value=3)
        with patch.object(app.audio, "play_many") as play, many as enq:
            await pilot.press("P")
            assert [e["id"] for e in play.call_args.args[0]] == [v["id"] for v in vids(1, 2, 3)]
            await pilot.press("S")
            assert sorted(e["id"] for e in play.call_args.args[0]) == [v["id"] for v in vids(1, 2, 3)]
            await pilot.press("E")
            assert len(enq.call_args.args[0]) == 3


def test_play_many_and_enqueue_many_on_the_controller(app):
    audio = app.audio
    a, b, c = ({"id": x, "title": x} for x in "abc")
    with patch.object(audio, "play_audio") as play, patch.object(app, "notify"):
        audio.play_many([a, b, c])
        assert play.call_args.args[0] is a and audio.queue == (b, c)
        audio._entry = a
        with patch.object(type(audio), "is_playing", True):
            assert audio.enqueue_many([a, b, {"id": "d"}]) == 1
        assert [e["id"] for e in audio.queue] == ["b", "c", "d"]


async def test_modal_selects_several_playlists_then_enter_flips_them_all(app):
    a = playlist.create("A")["id"]
    b = playlist.create("B", vids(1))["id"]
    c = playlist.create("C")["id"]
    entry = vids(1)[0]
    async with app.run_test(size=(110, 40)) as pilot:
        app.push_screen(PlaylistModal(entry))
        await pilot.pause(0.3)
        await pilot.press("space", "j", "space", "j")  # select A and B, cursor on C
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert item_ids(a) == [entry["id"]] and item_ids(b) == [] and item_ids(c) == []
        assert app.cache.get_video_raw(entry["id"]) is not None
        await pilot.press("k", "k", "enter")  # nothing selected: flips the highlighted one (A) off
        await pilot.pause(0.3)
        assert item_ids(a) == []
