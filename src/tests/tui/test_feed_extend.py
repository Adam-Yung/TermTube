"""Paging a feed must neither cancel the tab load nor land after the view changed."""

import threading

from textual.worker import WorkerState


def _entries(n, prefix):
    return [{"id": f"{prefix}{i:06d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


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

        def slow_batch(_panel):
            started.set()
            release.wait(5)
            return _entries(30, "late")

        screen._fetch_next_batch = slow_batch
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
