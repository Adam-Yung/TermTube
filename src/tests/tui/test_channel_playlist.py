"""A channel's playlist opened in the channel page: its videos, play all, enqueue all, save locally."""

from unittest.mock import MagicMock, patch

import pytest

from src import innertube, playlist
from src.tui.screens.channel_screen import ChannelScreen

URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
PL = {"id": "PLmix", "title": "Mix", "_playlist_name": "Mix", "_is_playlist": True, "url": "https://www.youtube.com/playlist?list=PLmix"}


def vids(prefix, n):
    return [{"id": f"{prefix}{i:010d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(innertube, "fetch_channel_page", lambda *a, **k: innertube.ChannelPage([]))
    monkeypatch.setattr(innertube, "fetch_channel_playlists", lambda cid: [PL])


async def settle(app, pilot):
    for _ in range(2):
        await app.workers.wait_for_complete()
        await pilot.pause()


async def open_playlist(app, pilot, monkeypatch, pages):
    served = list(pages)
    calls = []

    def fake(playlist_id, token="", **_):
        calls.append((playlist_id, token))
        return served.pop(0) if served else innertube.ChannelPage([])

    monkeypatch.setattr(innertube, "fetch_playlist_page", fake)
    app.push_screen(ChannelScreen(URL, "Chan"))
    await pilot.pause()
    await settle(app, pilot)
    screen = app.screen
    screen.query_one("#ch-tabs").active = "ch-tab-playlists"
    await settle(app, pilot)
    screen._activate_entry(PL)
    await settle(app, pilot)
    return screen, calls


async def test_enter_on_a_playlist_row_lists_its_videos_and_escape_returns_to_the_playlists(app, monkeypatch):
    async with app.run_test(size=(110, 34)) as pilot:
        screen, calls = await open_playlist(app, pilot, monkeypatch, [innertube.ChannelPage(vids("a", 3))])
        panel = screen._list()
        ids = [e["id"] for e in vids("a", 3)]
        assert calls == [("PLmix", "")] and [e["id"] for e in panel.visited_entries()] == ids
        assert "Mix" in str(panel.query_one("#list-breadcrumb").content)
        await pilot.press("escape")
        await pilot.pause()
        await settle(app, pilot)
        assert app.screen is screen and screen._playlist is None
        assert [e["id"] for e in panel.visited_entries()] == ["PLmix"]
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen


async def test_an_empty_playlist_page_falls_back_to_ytdlp(app, monkeypatch):
    import src.ytdlp as ytdlp

    monkeypatch.setattr(ytdlp, "fetch_page_batch", lambda url, *a, **k: vids("y", 2) if "PLmix" in url else [])
    async with app.run_test(size=(110, 34)) as pilot:
        screen, _ = await open_playlist(app, pilot, monkeypatch, [])
        assert [e["title"] for e in screen._list().visited_entries()] == ["y0", "y1"]


async def test_a_playlist_follows_its_continuation(app, monkeypatch):
    pages = [innertube.ChannelPage(vids("a", 30), "T1"), innertube.ChannelPage(vids("b", 5), "")]
    async with app.run_test(size=(110, 34)) as pilot:
        screen, calls = await open_playlist(app, pilot, monkeypatch, pages)
        assert calls == [("PLmix", ""), ("PLmix", "T1")] and screen._list().total_pages == 3


async def test_enqueue_all_play_all_use_every_loaded_video(app, monkeypatch):
    async with app.run_test(size=(110, 34)) as pilot:
        screen, calls = await open_playlist(app, pilot, monkeypatch, [innertube.ChannelPage(vids("a", 3))])
        app.audio.enqueue_many, app.audio.play_many = MagicMock(return_value=3), MagicMock()
        screen.action_enqueue_all()
        screen.action_play_all()
        assert len(app.audio.enqueue_many.call_args.args[0]) == 3 and len(app.audio.play_many.call_args.args[0]) == 3
        assert len(calls) == 1


async def test_bulk_fetches_the_rest_when_only_the_first_pages_are_loaded(app, monkeypatch):
    first = innertube.ChannelPage(vids("a", 20), "T1")
    pages = [first, innertube.ChannelPage([]), first, innertube.ChannelPage(vids("b", 5), "")]
    async with app.run_test(size=(110, 34)) as pilot:
        screen, calls = await open_playlist(app, pilot, monkeypatch, pages)
        app.audio.enqueue_many = MagicMock(return_value=25)
        screen._pager.token, screen._pager.fetching = "T1", False
        screen.action_enqueue_all()
        await settle(app, pilot)
        assert len(app.audio.enqueue_many.call_args.args[0]) == 25


async def test_a_gather_that_fails_part_way_enqueues_nothing_and_says_why(app, monkeypatch):
    from src.errors import NetworkDown

    first = innertube.ChannelPage(vids("a", 20), "T1")
    async with app.run_test(size=(110, 34)) as pilot:
        screen, calls = await open_playlist(app, pilot, monkeypatch, [first])

        def fail(playlist_id, token="", **_):
            if token:
                raise NetworkDown("x")
            return first

        monkeypatch.setattr(innertube, "fetch_playlist_page", fail)
        app.audio.enqueue_many = MagicMock(return_value=0)
        hints = []
        monkeypatch.setattr(ChannelScreen, "_hint", lambda self, msg, severity="warning": hints.append(msg))
        screen._pager.token, screen._pager.fetching = "T1", False
        screen.action_enqueue_all()
        await settle(app, pilot)
        assert not app.audio.enqueue_many.called and hints == ["Network error · r to retry"]


async def test_save_adds_the_videos_to_the_local_playlist_of_the_same_name(app, monkeypatch, temp_playlists):
    async with app.run_test(size=(110, 34)) as pilot:
        screen, _ = await open_playlist(app, pilot, monkeypatch, [innertube.ChannelPage(vids("a", 3))])
        with patch.object(app.cache, "put_video") as put:
            screen.action_save_list()
            screen.action_save_list()
        assert [i["id"] for i in playlist.find_by_name("Mix")["items"]] == [e["id"] for e in vids("a", 3)]
        assert put.call_count == 6


async def test_the_bulk_keys_say_to_open_a_playlist_first(app, monkeypatch):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        await settle(app, pilot)
        with patch.object(app.screen, "_hint") as hint:
            app.screen.action_enqueue_all()
        assert "Open a playlist first" in hint.call_args.args[0]
