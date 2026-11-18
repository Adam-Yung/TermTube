"""One Library tab with a left rail: collections, focus, filter tokens, download badges, narrow fallback."""

import json
from unittest.mock import patch

import pytest

from src import history, playlist
from src.tui.screens.nav_modal import NavModal
from src.tui.widgets.video_list import VideoListItem, VideoListPanel


@pytest.fixture(autouse=True)
def no_detail_network(monkeypatch, temp_playlists):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)


def add(directory, vid, ext="mp4", **info):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{vid}.{ext}").write_bytes(b"x" * 5)
    sidecar = {"id": vid, "title": f"Title {vid}", "upload_date": "20260101", **info}
    (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")


@pytest.fixture
def lib(app, tmp_path):
    videos, audio = tmp_path / "vid", tmp_path / "aud"
    add(videos, "v1", uploader="Alpha", duration=100)
    add(videos, "v2", uploader="Beta", duration=2000)
    add(audio, "a1", ext="mp3", uploader="Alpha", duration=200)
    app.config._data["video_dir"], app.config._data["audio_dir"] = str(videos), str(audio)
    return videos, audio


def panel_of(app) -> VideoListPanel:
    return app.screen.query_one("#video-list-panel", VideoListPanel)


def ids(app):
    return [c.entry["id"] for c in panel_of(app)._lv.children if isinstance(c, VideoListItem)]


async def open_library(app, pilot):
    await pilot.pause(0.8)
    await pilot.press("f5")
    await pilot.pause(0.6)


def rail_labels(app):
    return [i.label for i in app.screen._rail()._items]


async def test_tab_order_and_f_keys_have_no_playlists_tab(app):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.5)
        screen = app.screen
        from textual.widgets import Tabs

        tab_ids = [t.id for t in screen.query_one("#nav-tabs", Tabs).query("Tab")]
        assert tab_ids == ["home", "subscriptions", "search", "history", "library", "help"]
        await pilot.press("f5")
        await pilot.pause(0.5)
        assert screen.query_one("#nav-tabs", Tabs).active == "library" and screen._rail().display
        await pilot.press("f4")
        await pilot.pause(0.4)
        assert not screen._rail().display


async def test_f6_and_the_picker_open_help(app):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.5)
        await pilot.press("f6")
        await pilot.pause(0.3)
        assert "HelpScreen" in [type(s).__name__ for s in app.screen_stack]
        await pilot.press("escape")
        await pilot.pause(0.3)
        await pilot.press("grave_accent")
        await pilot.pause(0.2)
        assert isinstance(app.screen, NavModal)
        await pilot.press("5")
        await pilot.pause(0.5)
        assert app.screen._current_tab == "library"


async def test_h_and_l_cycle_through_the_remaining_tabs_and_wrap(app, monkeypatch):
    channels = [{"id": "c1", "title": "Chan", "_is_channel": True}]
    monkeypatch.setattr("src.ytdlp.fetch_subscribed_channels", lambda *a, **k: channels)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.6)
        seen = []
        for _ in range(5):
            await pilot.press("L")
            await pilot.pause(0.4)
            seen.append(app.screen._current_tab)
        assert seen == ["subscriptions", "history", "library", "home", "subscriptions"]
        await pilot.press("H", "H")
        await pilot.pause(0.5)
        assert app.screen._current_tab == "library"


async def test_rail_lists_collections_with_counts_and_playlists(app, lib):
    playlist.create("Mix", [{"id": "v1", "title": "T"}])
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        counts = [(i.label, i.count) for i in app.screen._rail()._items]
        assert counts == [("All downloads", 3), ("Videos", 2), ("Audio", 1), ("Mix", 1), ("+ New playlist", None)]
        assert ids(app) == ["v1", "v2", "a1"] or sorted(ids(app)) == ["a1", "v1", "v2"]


async def test_tab_moves_focus_enter_loads_a_collection_and_esc_returns(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        screen = app.screen
        assert not screen._rail_focused()
        await pilot.press("tab")
        assert screen._rail_focused()
        await pilot.press("j", "enter")  # Videos
        await pilot.pause(0.5)
        assert screen._current_tab == "library:video" and sorted(ids(app)) == ["v1", "v2"]
        assert not screen._rail_focused()
        await pilot.press("escape")
        assert screen._rail_focused()
        await pilot.press("j", "enter")  # Audio
        await pilot.pause(0.5)
        assert ids(app) == ["a1"]
        await pilot.press("tab")
        assert screen._rail_focused()
        await pilot.press("tab")
        assert not screen._rail_focused()


async def test_rail_keys_do_not_leak_to_the_list_and_row_actions_wait(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        screen = app.screen
        await pilot.press("tab", "j", "j")
        assert screen._rail().highlighted.label == "Audio"
        assert panel_of(app).selected_entry["id"] == ids(app)[0]
        assert screen._selected_entry() is None
        await pilot.press("l")  # to the list
        assert not screen._rail_focused()


async def test_tab_outside_the_library_only_hints(app):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.6)
        with patch.object(app.screen, "notify") as notify:
            await pilot.press("tab")
        assert "Library" in notify.call_args.args[0]


async def test_return_from_help_keeps_the_open_collection(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "j", "enter")
        await pilot.pause(0.4)
        await pilot.press("f6")
        await pilot.pause(0.3)
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert app.screen._current_tab == "library:video" and sorted(ids(app)) == ["v1", "v2"]


async def test_leaving_and_returning_restores_the_last_collection(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "j", "j", "enter")
        await pilot.pause(0.4)
        await pilot.press("f4")
        await pilot.pause(0.4)
        await pilot.press("f5")
        await pilot.pause(0.5)
        assert app.screen._current_tab == "library:audio" and app.screen._rail().current == "library:audio"


async def test_delete_in_a_collection_asks_the_library_question_and_updates_counts(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "j", "j", "enter")
        await pilot.pause(0.4)
        await pilot.press("D")
        await pilot.pause(0.1)
        targets, choices = app.screen._pending_remove
        assert targets[0]["id"] == "a1" and choices == {"y": "both"}
        await pilot.press("y")
        await pilot.pause(0.4)
        assert ids(app) == [] and app.screen._rail()._items[2].count == 0
        assert not (lib[1] / "a1.mp3").exists()


async def test_filter_tokens_apply_in_the_library_and_not_on_history(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("f", *"type:audio", "enter")
        await pilot.pause(0.4)
        assert ids(app) == ["a1"]
        await pilot.press("escape")
        await pilot.press("f", *"dur:>10m", "enter")
        await pilot.pause(0.4)
        assert ids(app) == ["v2"]
        await pilot.press("escape")
        await pilot.press("f", *"by:alpha", "enter")
        await pilot.pause(0.4)
        assert sorted(ids(app)) == ["a1", "v1"]


async def test_history_filter_is_plain_text(app, lib, temp_history):
    history.add({"id": "h1", "title": "type:audio talk", "uploader": "X"})
    history.add({"id": "h2", "title": "Other", "uploader": "X"})
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.6)
        await pilot.press("f4")
        await pilot.pause(0.5)
        await pilot.press("f", *"type:audio", "enter")
        await pilot.pause(0.4)
        assert ids(app) == ["h1"]


async def test_paging_and_filter_inside_a_big_collection(app, lib, tmp_path):
    for n in range(30):
        add(lib[0], f"p{n:02d}", uploader="Bulk")
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        panel = panel_of(app)
        await pilot.press("l")
        await pilot.pause(0.3)
        assert panel.current_page == 2
        await pilot.press("f", *"p07", "enter")
        await pilot.pause(0.4)
        assert ids(app) == ["p07"]


async def test_playlist_rows_show_download_badges_and_play_the_local_file(app, lib):
    pid = playlist.create("Mix", [
        {"id": "v1", "title": "Local video"}, {"id": "a1", "title": "Local audio"}, {"id": "zzz", "title": "Remote"},
    ])["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "j", "j", "j", "enter")
        await pilot.pause(0.5)
        assert app.screen._current_tab == f"playlist:{pid}"
        rows = {c.entry["id"]: c for c in panel_of(app)._lv.children if isinstance(c, VideoListItem)}
        assert [rows[k].entry["_dl"] for k in ("v1", "a1", "zzz")] == ["video", "audio", ""]
        assert "⬇ video" in rows["v1"]._cached_markup and "⬇ audio" in rows["a1"]._cached_markup
        assert "☁" in rows["zzz"]._cached_markup
        with patch.object(app.audio, "play_many") as play:
            await pilot.press("P")
        tracks = {t["id"]: t for t in play.call_args.args[0]}
        assert tracks["v1"]["_local_path"].endswith("v1.mp4") and "_local_path" not in tracks["zzz"]


async def test_detail_panel_lists_the_playlists_of_a_downloaded_item(app, lib):
    playlist.create("Mix", [{"id": "v1", "title": "T"}])
    playlist.create("Other", [{"id": "v1", "title": "T"}])
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        app.screen._detail().refresh_playlists("v1")
        text = str(app.screen._detail().query_one("#video-playlists").render())
        assert "In playlists:" in text and "Mix" in text and "Other" in text


async def test_new_playlist_entry_in_the_rail_opens_the_name_dialog(app, lib):
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "G", "enter")
        await pilot.pause(0.3)
        assert type(app.screen).__name__ == "NameModal"


async def test_deleting_the_shown_playlist_from_the_rail_returns_to_all_downloads(app, lib):
    pid = playlist.create("Gone", [{"id": "v1", "title": "T"}])["id"]
    async with app.run_test(size=(110, 40)) as pilot:
        await open_library(app, pilot)
        await pilot.press("tab", "j", "j", "j", "enter")
        await pilot.pause(0.4)
        await pilot.press("tab", "D", "y")
        await pilot.pause(0.5)
        assert playlist.get(pid) is None
        assert app.screen._current_tab == "library" and app.screen._rail_focused()
        await pilot.press("u")
        await pilot.pause(0.4)
        assert playlist.get(pid) is not None and "Gone" in rail_labels(app)


async def test_narrow_terminal_collapses_the_rail_to_one_line(app, lib):
    async with app.run_test(size=(80, 30)) as pilot:
        await open_library(app, pilot)
        rail = app.screen._rail()
        assert rail.narrow and rail.size.height == 1 and rail.size.width == 80
        assert panel_of(app).size.height > 5
        await pilot.press("tab", "j", "enter")
        await pilot.pause(0.5)
        assert app.screen._current_tab == "library:video" and sorted(ids(app)) == ["v1", "v2"]
        assert "Videos" in str(rail.render())


async def test_wide_terminal_shows_the_full_rail(app, lib):
    async with app.run_test(size=(120, 30)) as pilot:
        await open_library(app, pilot)
        assert not app.screen._rail().narrow and app.screen._rail().size.width == 23
