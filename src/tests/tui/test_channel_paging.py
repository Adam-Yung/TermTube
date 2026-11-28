"""Channel page paging: continuation tokens, prefetch on the second-to-last page, the cap, tab hiding."""

import threading
from functools import partial

import pytest
from textual.widgets import Tabs

from src import innertube
from src.tests.fakes import silence_detail_workers
from src.tui.screens.channel_screen import ChannelScreen

URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    silence_detail_workers(monkeypatch)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(innertube, "resolve_channel_id", lambda url: None)


def videos(n, prefix="v"):
    return [{"id": f"{prefix}{i:010d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


class Script:
    """Stands in for ``innertube.fetch_channel_page``: pages are served in order; every call is recorded."""

    def __init__(self, *pages):
        self.pages, self.calls = list(pages), []

    def __call__(self, channel_id, tab="videos", token="", **_):
        self.calls.append((tab, token))
        return self.pages.pop(0) if self.pages else innertube.ChannelPage([])


async def open_channel(app, pilot, script, monkeypatch):
    monkeypatch.setattr(innertube, "fetch_channel_page", script)
    app.push_screen(ChannelScreen(URL, "Chan"))
    await pilot.pause()
    screen = app.screen
    await settle(app, pilot)
    return screen


async def settle(app, pilot):
    for _ in range(2):
        await app.workers.wait_for_complete()
        await pilot.pause()


async def test_first_page_two_pages_long_prefetches_the_next_batch_at_once(app, monkeypatch):
    script = Script(innertube.ChannelPage(videos(30), "T1"), innertube.ChannelPage(videos(30, "w"), "T2"))
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await open_channel(app, pilot, script, monkeypatch)
        panel = screen._list()
        assert script.calls == [("videos", ""), ("videos", "T1")]
        assert panel.total_pages == 4
        assert screen._pager.token == "T2"


async def test_prefetch_waits_until_the_second_to_last_page(app, monkeypatch):
    script = Script(
        innertube.ChannelPage(videos(80), "T1"),
        innertube.ChannelPage(videos(20, "w"), "T2"),
        innertube.ChannelPage(videos(20, "x"), ""),
    )
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await open_channel(app, pilot, script, monkeypatch)
        panel = screen._list()
        assert panel.total_pages == 4 and script.calls == [("videos", "")]
        screen.action_page_next()
        assert script.calls == [("videos", "")]
        screen.action_page_next()
        await settle(app, pilot)
        assert script.calls[-1] == ("videos", "T1")
        assert panel.total_pages == 5


async def test_a_page_without_a_token_ends_fetching(app, monkeypatch):
    script = Script(innertube.ChannelPage(videos(30), "T1"), innertube.ChannelPage(videos(30, "w"), ""))
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await open_channel(app, pilot, script, monkeypatch)
        assert not screen._pager.token and len(script.calls) == 2
        screen.action_page_next()
        screen.action_page_next()
        await settle(app, pilot)
        assert len(script.calls) == 2


def _gated_pages(gate, second, channel_id, tab="videos", token="", **_):
    """The first page at once; the continuation only after ``gate`` opens."""
    if token:
        gate.wait(5)
        return second
    return innertube.ChannelPage(videos(20), "T1")


async def test_paging_past_the_last_page_waits_for_the_fetch_and_shows_it(app, monkeypatch):
    gate = threading.Event()
    second = innertube.ChannelPage(videos(20, "w"), "")

    monkeypatch.setattr(innertube, "fetch_channel_page", partial(_gated_pages, gate, second))
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        await pilot.pause(0.3)
        panel = screen._list()
        assert screen._pager.fetching and panel.total_pages == 1
        screen.action_page_next()
        assert panel.is_loading
        gate.set()
        await settle(app, pilot)
        assert panel.current_page == 2 and panel.selected_entry["id"].startswith("w")


async def test_a_tab_switch_drops_a_late_page_and_forgets_the_token(app, monkeypatch):
    script = Script(innertube.ChannelPage(videos(30), "T1"), innertube.ChannelPage(videos(30, "late"), "T2"))
    async with app.run_test(size=(110, 34)) as pilot:
        screen = await open_channel(app, pilot, script, monkeypatch)
        await app.workers.wait_for_complete()
        panel = screen._list()
        count = sum(len(p) for p in panel._pages.values())
        screen._pager.fetching = True
        screen._apply_extension(screen._content_session - 1, innertube.ChannelPage(videos(30, "old"), "T9"), False)
        assert sum(len(p) for p in panel._pages.values()) == count
        screen._start_content_load()
        assert screen._pager.token == "" and not screen._pager.fetching


async def test_progress_text_shows_while_fetching_and_clears_after(app, monkeypatch):
    async with app.run_test(size=(110, 34)) as pilot:
        script = Script(innertube.ChannelPage(videos(30), "T1"), innertube.ChannelPage(videos(30, "w"), ""))
        monkeypatch.setattr(innertube, "fetch_channel_page", script)
        monkeypatch.setattr(ChannelScreen, "_extend_content", lambda self, *a: None)
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        await settle(app, pilot)
        assert screen._pager.fetching and "loading 30 more" in screen._list()._status_note()
        screen._apply_extension(screen._content_session, innertube.ChannelPage(videos(30, "w"), ""), False)
        assert "loading" not in screen._list()._status_note()


async def test_tabs_the_channel_lacks_are_hidden_and_shorts_live_appear_when_present(app, monkeypatch):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        tabs = screen.query_one("#ch-tabs", Tabs)
        assert screen._tab_ids() == ["ch-tab-videos", "ch-tab-playlists"]
        assert not tabs.query_one("#ch-tab-shorts").display
        screen._show_tabs(("videos", "shorts", "live"))
        await pilot.pause()
        assert screen._tab_ids() == ["ch-tab-videos", "ch-tab-shorts", "ch-tab-live"]
        assert tabs.query_one("#ch-tab-shorts").display and not tabs.query_one("#ch-tab-playlists").display
        screen._cycle_tab(1)
        await pilot.pause()
        assert screen._current_tab == "ch-tab-shorts"
        screen._show_tabs(("videos", "playlists"))
        await pilot.pause()
        assert screen._current_tab == "ch-tab-videos"
