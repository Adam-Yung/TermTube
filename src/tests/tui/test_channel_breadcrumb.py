"""Channel page breadcrumb and back stack: a channel opened from a channel returns to where it came from."""

from unittest.mock import patch

import pytest
from textual.widgets import Static

from src.tui.fmt import fmt_breadcrumb
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.main_screen import MainScreen

ID_A = "UCuAXFkgsw1L7xaCfnd5JJOw"
ID_B = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
URL_A = f"https://www.youtube.com/channel/{ID_A}"


def test_breadcrumb_joins_and_collapses_the_middle():
    assert fmt_breadcrumb(["Home", "Chan", "Videos"]) == "Home › Chan › Videos"
    deep = ["Home", "A" * 20, "B" * 20, "C" * 20, "Videos"]
    assert fmt_breadcrumb(deep) == "Home › … › " + "C" * 20 + " › Videos"
    assert fmt_breadcrumb(["x" * 100]).startswith("…") and len(fmt_breadcrumb(["x" * 100])) == 70


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_load_content", lambda self, *a: None)


def crumb(screen) -> str:
    return str(screen._list().query_one("#list-breadcrumb", Static).content)


async def test_a_channel_opened_from_the_main_screen_shows_its_origin_tab(app):
    async with app.run_test(size=(110, 34)) as pilot:
        main = app.screen
        assert isinstance(main, MainScreen) and main._crumbs() == ["Home"]
        main._open_channel({"channel_url": URL_A, "uploader": "Chan A"})
        await pilot.pause()
        assert isinstance(app.screen, ChannelScreen)
        assert "Home › Chan A › Videos" in crumb(app.screen)


async def test_a_channel_opened_from_a_channel_stacks_and_escape_returns_to_the_first(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.screen._open_channel({"channel_url": URL_A, "uploader": "Chan A"})
        await pilot.pause()
        first = app.screen
        other = {"id": "AAAAAAAAAAA", "channel_id": ID_B, "uploader": "Chan B"}
        with patch.object(ChannelScreen, "_selected_entry", return_value=other):
            first.action_channel()
            await pilot.pause()
        second = app.screen
        assert second is not first and isinstance(second, ChannelScreen)
        assert "Home › Chan A › Chan B › Videos" in crumb(second)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is first


async def test_a_row_of_this_channel_does_not_open_itself_and_hides_the_menu_entry(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.screen._open_channel({"channel_url": URL_A, "uploader": "Chan A"})
        await pilot.pause()
        screen = app.screen
        own = {"id": "AAAAAAAAAAA", "channel_id": ID_A}
        bare = {"id": "BBBBBBBBBBB"}
        other = {"id": "CCCCCCCCCCC", "channel_id": ID_B}
        assert "channel" in screen._hidden_menu_actions(own) and "channel" in screen._hidden_menu_actions(bare)
        assert "channel" not in screen._hidden_menu_actions(other)
        with patch.object(ChannelScreen, "_selected_entry", return_value=own), patch.object(screen, "_hint") as hint:
            screen.action_channel()
        assert hint.call_args.args[0] == "Already on this channel." and app.screen is screen


async def test_the_breadcrumb_uses_the_channel_name_from_the_info_and_names_the_tab(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.screen._open_channel({"channel_url": URL_A, "uploader": "Chan A"})
        await pilot.pause()
        screen = app.screen
        screen._info_panel().update_info({"channel": "Real Name [x]", "channel_id": ID_A})
        screen._show_breadcrumb()
        assert "Home › Real Name [x] › Videos" in crumb(screen).replace("\\[", "[")
        screen.query_one("#ch-tabs").active = "ch-tab-playlists"
        await pilot.pause()
        assert crumb(screen).count("Playlists") == 1
