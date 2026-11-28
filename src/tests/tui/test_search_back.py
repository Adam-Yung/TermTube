"""Backspace on the Search tab goes back to the previous results, page and row; elsewhere it keeps its meaning."""

from functools import partial

import pytest
from textual.widgets import Tabs

from src.tests.fakes import silence_detail_workers


def _numbered_rows(query, config, cache, *, skip_ids=None, count=50, on_first_batch=None, **_):
    return [{"id": f"{query[:3]}{i:08d}", "title": f"{query} {i}"} for i in range(count)]


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    silence_detail_workers(monkeypatch)

    monkeypatch.setattr("src.ytdlp.fetch_search_batch", _numbered_rows)


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


async def test_backspace_on_the_library_goes_to_the_rail_and_keeps_the_search(app, temp_playlists):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._show_search_results("alpha")
        await pilot.pause(0.4)
        screen._show_search_results("beta")
        await pilot.pause(0.4)
        screen.query_one("#nav-tabs", Tabs).active = "library"
        await pilot.pause(0.4)
        await pilot.press("backspace")
        await pilot.pause(0.3)
        assert screen._rail_focused() and screen._current_tab == "library" and screen._search.query == "beta"


def _filtered_rows(calls, query, config, cache, *, skip_ids=None, count=50, on_first_batch=None,
                   sort="relevance", kind="all"):
    calls.append((sort, kind))
    return [{"id": f"{sort[:2]}{kind[:2]}{i:07d}", "title": f"{sort} {kind} {i}"} for i in range(12)]


async def test_s_and_t_filter_the_search_and_reload_it(app, monkeypatch):
    calls = []

    monkeypatch.setattr("src.ytdlp.fetch_search_batch", partial(_filtered_rows, calls))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._show_search_results("alpha")
        await pilot.pause(0.5)
        await pilot.press("s")
        await pilot.pause(0.2)
        await pilot.press("2")
        await pilot.pause(0.6)
        await pilot.press("t")
        await pilot.pause(0.2)
        await pilot.press("c")
        await pilot.pause(0.6)
        assert calls[-1] == ("date", "channel") and (screen._search.sort, screen._search.kind) == ("date", "channel")
        assert "channels only" in screen._list()._breadcrumb.content


async def test_s_and_t_on_other_tabs_only_hint(app):
    from unittest.mock import patch

    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        with patch.object(screen, "notify") as notify:
            await pilot.press("s")
            await pilot.pause(0.2)
        assert type(app.screen).__name__ == "MainScreen"
        assert "search results" in notify.call_args.args[0]


async def test_enter_on_a_search_playlist_row_opens_the_playlist_page(app, monkeypatch):
    from src import innertube

    monkeypatch.setattr(innertube, "fetch_playlist_page", lambda *a, **k: innertube.ChannelPage([]))
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._current_tab = "search"
        screen._activate_entry({"id": "PLx", "_is_playlist": True, "_playlist_name": "x"})
        await pilot.pause(0.1)
        assert type(app.screen).__name__ == "ChannelScreen" and app.screen._playlist["id"] == "PLx"
        assert app.screen._trail == ["Search"]


def _one_new_row(asked, query, config, cache, *, skip_ids=None, count=50, **_):
    asked.append(count)
    return [{"id": "new"}]


def test_search_extension_asks_for_what_is_left_below_the_200_cap(monkeypatch):
    from types import SimpleNamespace

    from src.tui.screens.mixins.feed_loader import FeedLoaderMixin

    asked = []

    monkeypatch.setattr("src.ytdlp.fetch_search_batch", partial(_one_new_row, asked))
    app = SimpleNamespace(config=None, cache=None)
    for seen, expected in ((50, [50]), (180, [20]), (200, [])):
        asked.clear()
        host = SimpleNamespace(
            app=app, _current_tab="search", _search=SimpleNamespace(query="q", sort="date", kind="all")
        )
        rows = FeedLoaderMixin._fetch_next_batch(host, SimpleNamespace(seen_ids={f"s{i}" for i in range(seen)}))
        assert asked == expected and bool(rows) == bool(expected)


def _two_hundred_rows(query, config, cache, **_):
    return _numbered_rows(query, config, cache, count=200)


async def test_going_back_restores_a_page_beyond_the_first_fifty(app, monkeypatch):
    monkeypatch.setattr("src.ytdlp.fetch_search_batch", _two_hundred_rows)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        panel = screen._list()
        screen._show_search_results("alpha")
        await pilot.pause(0.6)
        last = max(panel._pages)
        target = panel._pages[last][0]["id"]
        panel.load_page(last, focus_id=target)
        await pilot.pause(0.2)
        screen._show_search_results("beta")
        await pilot.pause(0.6)
        await pilot.press("backspace")
        await pilot.pause(0.7)
        assert panel.current_page == last and panel.selected_entry["id"] == target
        assert int(target[3:]) >= 150
