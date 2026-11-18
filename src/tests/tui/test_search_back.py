"""Backspace on the Search tab goes back to the previous results, page and row; elsewhere it keeps its meaning."""

import pytest
from textual.widgets import Tabs


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)

    def results(query, config, cache, *, skip_ids=None, count=50, on_first_batch=None):
        return [{"id": f"{query[:3]}{i:08d}", "title": f"{query} {i}"} for i in range(count)]

    monkeypatch.setattr("src.ytdlp.fetch_search_batch", results)


async def test_backspace_returns_to_the_previous_query_page_and_row(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        panel = screen._list()
        screen._show_search_results("alpha")
        await pilot.pause(0.5)
        target = panel._pages[2][4]["id"]
        panel.load_page(2, focus_id=target)
        await pilot.pause(0.2)
        screen._show_search_results("beta")
        await pilot.pause(0.5)
        assert screen._search.query == "beta"
        assert "alpha" in panel._breadcrumb.content
        await pilot.press("backspace")
        await pilot.pause(0.6)
        assert screen._search.query == "alpha"
        assert panel.current_page == 2
        assert panel.selected_entry["id"] == target


async def test_backspace_with_one_search_does_nothing(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._show_search_results("alpha")
        await pilot.pause(0.5)
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert screen._search.query == "alpha" and screen._current_tab == "search"


async def test_backspace_on_another_tab_leaves_the_stack_alone(app, monkeypatch):
    monkeypatch.setattr("src.history.all_entries", lambda: [{"id": "h1", "title": "h"}])
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._show_search_results("alpha")
        await pilot.pause(0.4)
        screen._show_search_results("beta")
        await pilot.pause(0.4)
        screen.query_one("#nav-tabs", Tabs).active = "history"
        await pilot.pause(0.4)
        await pilot.press("backspace")
        await pilot.pause(0.3)
        assert screen._search.query == "beta" and screen._current_tab == "history"


async def test_backspace_in_a_playlist_still_goes_to_the_playlist_index(app, monkeypatch):
    monkeypatch.setattr("src.playlist.list_names", lambda: ["mix"])
    monkeypatch.setattr("src.playlist.get_playlist", lambda name: [])
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._show_search_results("alpha")
        await pilot.pause(0.4)
        screen._show_search_results("beta")
        await pilot.pause(0.4)
        screen.query_one("#nav-tabs", Tabs).active = "playlists"
        await pilot.pause(0.4)
        screen._open_playlist("mix")
        await pilot.pause(0.3)
        await pilot.press("backspace")
        await pilot.pause(0.4)
        assert screen._current_tab == "playlists" and screen._search.query == "beta"
