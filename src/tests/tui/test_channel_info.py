"""Channel info column: description folded to three lines, `i` toggles, video count and join date."""

import pytest
from textual.widgets import Static

from src.tui.screens.channel_screen import ChannelScreen
from src.tui.widgets.channel_info_panel import _collapse, _stats

URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
LONG = "\n".join(f"line {n}" for n in range(1, 8))


def test_collapse_keeps_three_lines_and_says_when_more_remains():
    assert _collapse(LONG) == ("line 1\nline 2\nline 3", True)
    assert _collapse("one\ntwo") == ("one\ntwo", False)
    assert _collapse("") == ("", False)


def test_collapse_cuts_a_very_long_line():
    shown, more = _collapse("x" * 300)
    assert more and shown == "x" * 120 + "…"


def test_stats_use_whichever_of_count_and_join_date_exist():
    assert _stats({"video_count": 442, "joined": "Joined Mar 3, 2011"}) == "442 videos · Joined Mar 3, 2011"
    assert _stats({"video_count": 1}) == "1 video"
    assert _stats({"joined": "Joined 2011"}) == "Joined 2011"
    assert _stats({}) == ""


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_load", lambda self: None)


def text(screen, selector):
    return str(screen.query_one(selector, Static).content)


async def test_i_expands_and_collapses_the_description(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        screen._info_panel().update_info({"channel": "Chan", "description": LONG, "video_count": 442})
        assert text(screen, "#ch-desc") == "line 1\nline 2\nline 3" and "show all" in text(screen, "#ch-desc-hint")
        assert "442 videos" in text(screen, "#ch-stats")
        await pilot.press("i")
        assert text(screen, "#ch-desc") == LONG and "show less" in text(screen, "#ch-desc-hint")
        await pilot.press("i")
        assert text(screen, "#ch-desc") == "line 1\nline 2\nline 3"


async def test_i_on_a_short_description_says_there_is_nothing_more(app):
    from unittest.mock import patch

    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        screen._info_panel().update_info({"channel": "Chan", "description": "short"})
        assert text(screen, "#ch-desc-hint") == ""
        with patch.object(screen, "_hint") as hint:
            await pilot.press("i")
        assert hint.call_args.args[0] == "Nothing more to show."


async def test_a_new_channel_info_collapses_again(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Chan"))
        await pilot.pause()
        screen = app.screen
        panel = screen._info_panel()
        panel.update_info({"channel": "Chan", "description": LONG})
        panel.toggle_description()
        panel.update_info({"channel": "Chan", "description": LONG})
        assert text(screen, "#ch-desc") == "line 1\nline 2\nline 3"
