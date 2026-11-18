"""The search prompt: history rows, filtering as you type, Up/Down, Ctrl+D."""

import pytest

from src import search_history
from src.tui.screens.search_modal import SearchModal


@pytest.fixture
def modal_app(app):
    for q in ("python tips", "rust guide", "learn rust"):
        search_history.add(q)
    return app


def rows(modal):
    return modal._candidates


async def test_empty_input_lists_recent_queries(modal_app):
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        assert rows(modal_app.screen) == ["learn rust", "rust guide", "python tips"]


async def test_typing_filters_prefix_first(modal_app):
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        await pilot.press(*"rust")
        await pilot.pause(0.2)
        assert rows(modal_app.screen) == ["rust guide", "learn rust"]


async def test_down_then_enter_submits_the_highlighted_query(modal_app):
    results = []
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal(), results.append)
        await pilot.pause(0.2)
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.2)
    assert results == ["rust guide"]


async def test_enter_without_highlight_submits_the_typed_text(modal_app):
    results = []
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal(), results.append)
        await pilot.pause(0.2)
        await pilot.press(*"new", "enter")
        await pilot.pause(0.2)
    assert results == ["new"]


async def test_ctrl_d_forgets_the_highlighted_query(modal_app):
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        await pilot.press("down", "ctrl+d")
        await pilot.pause(0.2)
        assert search_history.all_queries() == ["rust guide", "python tips"]
        assert rows(modal_app.screen) == ["rust guide", "python tips"]


async def test_history_off_shows_no_rows(modal_app):
    modal_app.config.set("search_history", False)
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        assert rows(modal_app.screen) == []


async def test_a_submitted_search_is_recorded(modal_app, monkeypatch):
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_search_results", lambda self, q: None)
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.screen._open_search_dialog()
        await pilot.pause(0.2)
        await pilot.press(*"zebra", "enter")
        await pilot.pause(0.3)
        assert search_history.all_queries()[0] == "zebra"
