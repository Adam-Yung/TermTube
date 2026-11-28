"""The hooks and messages the lists and loaders call reach the intended implementation on the real screens.

Each test spies on the real method through the class (so a shadowing mixin makes the spy miss) and drives the
screen through its actions, keys and messages.
"""

from functools import partialmethod

import pytest
from textual.widgets import Tabs

from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.main_screen import MainScreen
from src.tui.screens.mixins.feed_loader import FeedLoaderMixin
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.widgets.video_list import VideoListPanel

URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)


def _record_call(self, calls, forward, *args, **kwargs):
    calls.append((args, kwargs))
    return forward(self, *args, **kwargs) if forward else None


def spy(monkeypatch, cls, name, *, through=False):
    """Record calls to ``cls.name``; with ``through`` the real method still runs."""
    real, calls = getattr(cls, name), []

    monkeypatch.setattr(cls, name, partialmethod(_record_call, calls, real if through else None))
    return calls


def rows(n, prefix="seed"):
    return [{"id": f"{prefix}{i:06d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]

async def reach_page(pilot, panel, page):
    """Wait (bounded, on state) until the panel shows ``page``; a slow runner may lag a fixed pause."""
    for _ in range(100):
        if panel.current_page == page:
            return
        await pilot.pause(0.05)


async def seed(app, pilot, tab, pages):
    screen = app.screen
    await pilot.pause(0.3)
    panel = screen._list()
    panel.clear_and_set_loading()
    panel.add_entries(1, rows(pages * panel.page_size))
    panel.load_page(1)
    panel.finish_loading()
    screen._current_tab = tab
    screen._close_cursor()
    return screen, panel


def test_the_loader_hooks_resolve_to_the_loader_on_the_main_screen():
    for hook in ("_on_page_shown", "_on_past_last_page"):
        assert getattr(MainScreen, hook) is getattr(FeedLoaderMixin, hook)
        assert getattr(MainScreen, hook) is not getattr(ListNavMixin, hook, None)
        assert getattr(ChannelScreen, hook).__qualname__.startswith("ChannelScreen.")


async def test_home_asks_for_more_on_the_second_to_last_page_and_past_the_end(app, monkeypatch):
    calls = spy(monkeypatch, FeedLoaderMixin, "_request_extension")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, "home", 3)
        screen.action_page_next()
        await reach_page(pilot, panel, 2)
        assert panel.current_page == 2 and calls == [((), {"show": False})]
        screen.action_page_next()
        screen.action_page_next()
        await reach_page(pilot, panel, 3)
        assert panel.current_page == 3 and calls[-1] == ((), {"show": True})


async def test_search_asks_for_more_only_on_its_last_page(app, monkeypatch):
    calls = spy(monkeypatch, FeedLoaderMixin, "_request_extension")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, "search", 3)
        screen.action_page_next()
        await reach_page(pilot, panel, 2)
        assert panel.current_page == 2 and calls == []
        screen.action_page_next()
        await reach_page(pilot, panel, 3)
        assert panel.current_page == 3 and calls == [((), {"show": False})]


@pytest.mark.parametrize("tab", ["subscriptions", "following", "history", "library", "library:audio", "playlist:p1"])
async def test_tabs_that_hold_everything_never_ask_for_more(app, monkeypatch, tab):
    calls = spy(monkeypatch, FeedLoaderMixin, "_request_extension")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, tab, 2)
        for _ in range(3):
            screen.action_page_next()
        screen.action_goto_end()
        await reach_page(pilot, panel, 2)
        await pilot.pause(0.1)
        assert panel.current_page == 2 and calls == []


@pytest.mark.parametrize("tab", ["home", "search"])
async def test_an_active_filter_blocks_extension(app, monkeypatch, tab):
    calls = spy(monkeypatch, FeedLoaderMixin, "_request_extension")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, tab, 2)
        panel._filter = "seed"
        screen._on_page_shown()
        screen._on_past_last_page()
        assert calls == []


async def test_a_tab_switch_cancels_the_loads_and_forgets_a_waiting_extension(app, monkeypatch):
    monkeypatch.setattr("src.history.all_entries", lambda: [{"id": "h1", "title": "h"}])
    cancelled = spy(monkeypatch, MainScreen, "_cancel_pending_focus_and_thumb", through=True)
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, "home", 2)
        session = screen._feed_session
        screen._pending_show = True
        screen.query_one("#nav-tabs", Tabs).active = "history"
        await pilot.pause(0.4)
        assert cancelled and screen._feed_session > session
        assert screen._pending_show is False and screen._feed_cursor is None


@pytest.mark.parametrize("tab", ["home", "subscriptions", "history", "search", "library:video", "following"])
async def test_r_reloads_the_current_tab(app, monkeypatch, tab):
    loads = spy(monkeypatch, MainScreen, "_load_view")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, tab, 1)
        loads.clear()
        cleared = spy(monkeypatch, type(app.cache), "clear_feed", through=True)
        await pilot.press("r")
        await pilot.pause(0.1)
        assert loads == [((tab,), {})]
        assert bool(cleared) == (tab == "home")


async def test_escape_closes_a_kept_filter_before_it_goes_to_the_side_list(app, monkeypatch):
    loads = spy(monkeypatch, MainScreen, "_load_view")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, "following", 1)
        loads.clear()
        panel._filter = "seed"
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not panel.filter_active and screen._current_tab == "following" and loads == []
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen._rail_focused() and screen._current_tab == "following" and loads == []


async def test_escape_on_home_does_nothing(app, monkeypatch):
    loads = spy(monkeypatch, MainScreen, "_load_view")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, "home", 1)
        loads.clear()
        await pilot.press("backspace")
        await pilot.pause(0.1)
        assert screen._current_tab == "home" and loads == []


async def test_escape_in_the_library_moves_to_the_rail(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, "library", 1)
        screen._rail().display = True
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen._rail_focused()


@pytest.mark.parametrize("direction, action", [(1, "action_page_next"), (-1, "action_page_prev")])
async def test_the_panels_page_requests_reach_the_screens_page_actions(app, monkeypatch, direction, action):
    called = spy(monkeypatch, ListNavMixin, action)
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, "history", 2)
        screen.post_message(VideoListPanel.PageChangeRequested(direction))
        await pilot.pause(0.1)
        assert len(called) == 1


async def test_selected_and_activated_reach_the_main_screen(app, monkeypatch):
    focused = spy(monkeypatch, MainScreen, "_focus_video")
    activated = spy(monkeypatch, MainScreen, "action_activate")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await seed(app, pilot, "history", 1)
        entry = rows(1)[0]
        screen.post_message(VideoListPanel.Selected(entry))
        screen.post_message(VideoListPanel.Activated(entry))
        await pilot.pause(0.1)
        assert focused and activated


async def test_a_removal_and_its_undo_both_run_the_rail_refresh(app, monkeypatch):
    from src.tui.screens.mixins.library_rail import LibraryRailMixin
    from src.tui.screens.mixins.list_tools import Removal

    after = spy(monkeypatch, LibraryRailMixin, "_after_removal")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await seed(app, pilot, "history", 1)
        held = rows(2)
        screen._removals = lambda: {"history": Removal(lambda t, c: t, lambda r: None, lambda: held, "item")}
        screen._remove(held[:1], "")
        screen.action_undo()
        assert len(after) == 2


@pytest.fixture
def channel(monkeypatch):
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr("src.innertube.resolve_channel_id", lambda url: None)


async def open_channel(app, pilot, pages):
    app.push_screen(ChannelScreen(URL, "Chan"))
    await pilot.pause()
    screen = app.screen
    panel = screen._list()
    panel.clear_and_set_loading()
    panel.add_entries(1, rows(pages * panel.page_size))
    panel.load_page(1)
    panel.finish_loading()
    return screen, panel


async def test_the_channel_pager_prefetches_and_extends_past_the_end(app, channel, monkeypatch):
    calls = spy(monkeypatch, ChannelScreen, "_extend")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await open_channel(app, pilot, 3)
        screen._pager.start(3 * panel.page_size, "T1")
        calls.clear()
        screen.action_page_next()
        assert panel.current_page == 2 and calls == [((), {"show": False})]
        screen.action_page_next()
        screen.action_page_next()
        assert ((), {"show": True}) in calls


async def test_the_channel_filter_blocks_extension(app, channel, monkeypatch):
    calls = spy(monkeypatch, ChannelScreen, "_extend_content")
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await open_channel(app, pilot, 2)
        screen._pager.start(2 * panel.page_size, "T1")
        panel._filter = "seed"
        calls.clear()  # the screen's own startup load may still extend once, before the filter
        screen._on_past_last_page()
        screen._maybe_prefetch()
        assert calls == []


async def test_the_channel_page_requests_and_selection_reach_its_own_handlers(app, channel, monkeypatch):
    focused = spy(monkeypatch, ChannelScreen, "_focus_video")
    paged = spy(monkeypatch, ChannelScreen, "action_page_next", through=True)
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await open_channel(app, pilot, 2)
        screen.post_message(VideoListPanel.PageChangeRequested(1))
        screen.post_message(VideoListPanel.Selected(rows(1)[0]))
        await pilot.pause(0.1)
        assert len(paged) == 1 and focused


async def test_escape_on_a_channel_page_closes_the_filter_then_leaves(app, channel):
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await open_channel(app, pilot, 1)
        panel._filter = "seed"
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.screen is screen and not panel.filter_active
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.screen is not screen
