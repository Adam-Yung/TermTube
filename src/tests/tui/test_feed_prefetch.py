"""Home extension: cursor continuation, second-to-last-page prefetch, one in flight, progress text, typed errors."""

import threading

import pytest

from src.errors import RateLimited


def _entries(n, prefix):
    return [{"id": f"{prefix}{i:06d}"[:11], "title": f"{prefix}{i}"} for i in range(n)]


class _Cursor:
    """Records each advance; ``gate`` holds a take until released."""

    def __init__(self, rows=40, gate=None, error=None):
        self.calls, self.ids, self.exhausted, self.closed = [], [], False, False
        self._rows, self._gate, self._error, self._n = rows, gate, error, 0

    def take(self, count, skip_ids, **_):
        self.calls.append((count, len(skip_ids)))
        if self._gate:
            self._gate.wait(5)
        if self._error:
            raise self._error
        self._n += 1
        return _entries(self._rows, f"x{self._n}")

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)


async def _setup(app, pilot, pages, cursor):
    screen = app.screen
    await pilot.pause(0.3)
    panel = screen._list()
    panel.clear_and_set_loading()
    panel.add_entries(1, _entries(pages * panel.page_size, "seed"))
    panel.load_page(1)
    panel.finish_loading()
    screen._current_tab = "home"
    screen._feed_cursor = cursor
    return screen, panel


async def test_reaching_the_second_to_last_page_prefetches_once(app):
    gate = threading.Event()
    cursor = _Cursor(gate=gate)
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await _setup(app, pilot, 3, cursor)
        screen.action_page_next()
        await pilot.pause(0.2)
        assert panel.current_page == 2
        assert "loading 80 more" in panel._status_note()
        screen.action_page_next()
        screen.action_goto_end()
        await pilot.pause(0.2)
        assert len(cursor.calls) == 1 and cursor.calls[0][0] == 80
        gate.set()
        await pilot.pause(0.4)
        assert panel.total_pages > 3
        assert f"{panel.loaded_count} loaded" in panel._status_note()


async def test_an_early_page_does_not_prefetch(app):
    cursor = _Cursor()
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await _setup(app, pilot, 4, cursor)
        screen.action_page_next()
        await pilot.pause(0.2)
        assert panel.current_page == 2 and not cursor.calls


async def test_paging_past_the_end_while_prefetching_shows_the_new_page(app):
    gate = threading.Event()
    cursor = _Cursor(gate=gate)
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await _setup(app, pilot, 2, cursor)
        screen.action_page_next()
        await pilot.pause(0.2)
        screen.action_page_next()
        await pilot.pause(0.1)
        assert panel.is_loading and len(cursor.calls) == 1
        gate.set()
        await pilot.pause(0.4)
        assert not panel.is_loading and panel.current_page == 3


async def test_no_extension_while_a_filter_is_active(app):
    cursor = _Cursor()
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await _setup(app, pilot, 2, cursor)
        panel._filter = "seed"
        screen._on_page_shown()
        assert not screen._can_extend() and not cursor.calls


async def test_an_extension_error_is_typed_and_visible(app):
    cursor = _Cursor(error=RateLimited("429"))
    async with app.run_test(size=(100, 30)) as pilot:
        screen, panel = await _setup(app, pilot, 2, cursor)
        screen.action_page_next()
        await pilot.pause(0.4)
        assert "⚠" in panel._status_note() and "rate" in panel._status_note().lower()
        assert screen._extending_session is None


async def test_changing_view_closes_the_cursor(app):
    cursor = _Cursor()
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await _setup(app, pilot, 2, cursor)
        screen._load_view("history")
        assert cursor.closed and screen._feed_cursor is None


async def test_an_exhausted_feed_stops_extending(app):
    cursor = _Cursor()
    cursor.exhausted = True
    async with app.run_test(size=(100, 30)) as pilot:
        screen, _panel = await _setup(app, pilot, 2, cursor)
        assert not screen._can_extend()
