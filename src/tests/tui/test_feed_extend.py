"""Paging a feed must neither cancel the tab load nor land after the view changed."""

import threading
from functools import partial

from textual.worker import WorkerState


def _entries(n, prefix):
    return [{"id": f"{prefix}{i:06d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


def _late_batch(started, release, _panel):
    started.set()
    release.wait(5)
    return _entries(30, "late")


def _late_home(screen, started, release, feed_key, panel):
    """A tab load that delivers its rows only after ``release``."""
    started.set()
    release.wait(5)
    screen._ui(panel.add_entries, 1, _entries(30, "late"))
    screen._ui(panel.load_page, 1)


async def test_extend_does_not_cancel_the_running_tab_load(app):
    release = threading.Event()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._load_feed = lambda feed_key, panel: release.wait(5)
        screen._fetch_next_batch = lambda panel: _entries(5, "ext")
        screen._load_view("home")
        await pilot.pause(0.2)
        load = next(w for w in screen.workers if w.group == "feed_loader")
        assert load.state == WorkerState.RUNNING
        screen._extend_feed(show=False, session=screen._feed_session)
        await pilot.pause(0.3)
        assert load.state == WorkerState.RUNNING
        release.set()
        await pilot.pause(0.3)
        assert load.state == WorkerState.SUCCESS


async def test_an_extension_from_before_a_view_change_is_dropped(app):
    started, release = threading.Event(), threading.Event()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        panel = screen._list()
        before = panel.total_pages
        screen._fetch_next_batch = partial(_late_batch, started, release)
        screen._extend_feed(show=False, session=screen._feed_session)
        await pilot.pause(0.1)
        assert started.wait(2)
        screen._feed_session += 1
        release.set()
        await pilot.pause(0.3)
        assert panel.total_pages == before


async def test_an_extension_in_the_current_view_is_applied(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        panel = screen._list()
        before = panel.total_pages
        screen._fetch_next_batch = lambda _panel: _entries(30, "good")
        screen._extend_feed(show=False, session=screen._feed_session)
        await pilot.pause(0.3)
        assert panel.total_pages > before


async def test_local_lists_are_split_into_pages(app, monkeypatch):
    from src import history

    monkeypatch.setattr(history, "all_entries", lambda: _entries(45, "hist"))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._load_view("history")
        await pilot.pause(0.5)
        panel = screen._list()
        assert panel.total_pages == 3
        assert panel.can_go_next()


async def test_a_long_local_list_keeps_every_page(app, monkeypatch):
    from src import history

    monkeypatch.setattr(history, "all_entries", lambda: _entries(650, "long"))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._load_view("history")
        await pilot.pause(0.5)
        panel = screen._list()
        assert panel.total_pages == 33
        assert panel.load_page(2)


async def test_a_slow_home_load_does_not_land_in_the_next_tab(app, monkeypatch):
    from textual.widgets import Tabs

    from src import history

    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(history, "all_entries", lambda: _entries(3, "hist"))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen

        screen._load_feed = partial(_late_home, screen, started, release)
        screen._load_view("home")
        await pilot.pause(0.1)
        assert started.wait(2)
        screen.query_one("#nav-tabs", Tabs).active = "history"
        await pilot.pause(0.4)
        panel = screen._list()
        assert [e["id"] for e in panel.visited_entries()] == [e["id"] for e in _entries(3, "hist")]
        release.set()
        await pilot.pause(0.4)
        assert panel.total_pages == 1
        assert not any(e["id"].startswith("late") for e in panel.visited_entries())
