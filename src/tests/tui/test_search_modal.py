"""The search prompt: history rows, filtering as you type, Up/Down, Ctrl+D."""

import pytest

from src import search_history
from src.tui.screens.search_modal import SearchModal


@pytest.fixture
def modal_app(app, monkeypatch):
    monkeypatch.setattr("src.tui.screens.search_modal._DEBOUNCE_S", 0.01)  # tests wait on workers, not on the debounce
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


# Suggestions as you type (the fetch is faked; nothing here touches the network)

async def type_and_wait(pilot, text, wait=0.5):
    await pilot.press(*text)
    await pilot.pause(wait)


async def test_suggestions_follow_history_rows_deduped_and_capped(modal_app, monkeypatch):
    found = ["rust guide", "RUST async", *[f"rust {i}" for i in range(10)]]
    monkeypatch.setattr("src.innertube.fetch_suggestions", lambda q, **_: found)
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        await type_and_wait(pilot, "rust")
        got = rows(modal_app.screen)
        assert got[:2] == ["rust guide", "learn rust"]
        assert got[2] == "RUST async" and len(got) == 8
        assert [g.casefold() for g in got].count("rust guide") == 1


async def test_no_request_below_two_characters_or_when_switched_off(modal_app, monkeypatch):
    calls = []
    monkeypatch.setattr("src.innertube.fetch_suggestions", lambda q, **_: calls.append(q) or ["x"])
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        await type_and_wait(pilot, "r")
        assert calls == []
        modal_app.config._data["search_suggestions"] = False
        await type_and_wait(pilot, "u")
        assert calls == []


async def test_typing_fast_sends_one_request_for_the_last_text(modal_app, monkeypatch):
    monkeypatch.setattr("src.tui.screens.search_modal._DEBOUNCE_S", 600.0)
    calls = []
    monkeypatch.setattr("src.innertube.fetch_suggestions", lambda q, **_: calls.append(q) or [])
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        await type_and_wait(pilot, "rust", wait=0.1)
        assert calls == []  # the debounce has not fired however slow the machine is
        modal = modal_app.screen
        modal._debounce.stop()
        modal._fetch_suggestions("rust", modal._seq)  # what the timer does once typing pauses
        await pilot.pause(0.5)
    assert calls == ["rust"]


async def test_a_late_answer_for_older_text_is_ignored(modal_app):
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal())
        await pilot.pause(0.2)
        modal = modal_app.screen
        await pilot.press(*"zz")
        stale = modal._seq
        await pilot.press("z")
        modal._apply_suggestions(stale, ["old answer"])
        assert "old answer" not in rows(modal)
        modal._apply_suggestions(modal._seq, ["new answer"])
        assert "new answer" in rows(modal)


async def test_a_suggestion_can_be_picked_with_the_arrows(modal_app, monkeypatch):
    monkeypatch.setattr("src.innertube.fetch_suggestions", lambda q, **_: ["python asyncio"])
    results = []
    async with modal_app.run_test(size=(100, 30)) as pilot:
        modal_app.push_screen(SearchModal(), results.append)
        await pilot.pause(0.2)
        await type_and_wait(pilot, "py")
        await pilot.press("up", "enter")
        await pilot.pause(0.2)
    assert results == ["python asyncio"]


async def test_settings_toggle_turns_suggestions_off_and_back_on(app):
    from textual.widgets import ListView

    from src.tui.screens.settings_modal import SettingsModal

    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(SettingsModal())
        await pilot.pause(0.3)
        lv = app.screen.query_one("#suggest-list", ListView)
        lv.focus()
        await pilot.pause(0.1)
        lv.index = 1
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert not app.config.search_suggestions_enabled
        lv.index = 0
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app.config.search_suggestions_enabled
