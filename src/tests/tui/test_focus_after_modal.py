"""Closing a dialog with Esc returns focus to the list the user was on, with the cursor where it was."""

import pytest
from textual.widgets import ListView, Tabs

from src.tests.tui.test_screen_layout_audit import fake_data, main_app  # noqa: F401  (fixtures)

# (tab, keys that open the dialog)
OPENERS = [
    ("home", "enter"),
    ("home", "p"),
    ("home", "d"),
    ("home", "V"),
    ("home", "A"),
    ("home", "comma"),
    ("home", "question_mark"),
    ("home", "slash"),
    ("history", "s"),
    ("library", "n"),
    ("library", "grave_accent"),
]


@pytest.mark.parametrize(("tab", "key"), OPENERS, ids=lambda v: str(v))
async def test_escape_returns_focus_to_the_list_and_keeps_the_cursor(main_app, tab, key):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        if tab != "home":
            main_app.screen.query_one("#nav-tabs", Tabs).active = tab
            await pilot.pause(0.8)
        screen = main_app.screen
        await pilot.press("j", "j")
        await pilot.pause(0.3)
        lv = screen._list().query_one("#list-view", ListView)
        before = lv.index
        await pilot.press(key)
        await pilot.pause(0.4)
        assert main_app.screen is not screen, f"{key} opened nothing"
        await pilot.press("escape")
        await pilot.pause(0.4)
        assert main_app.screen is screen
        assert main_app.focused is lv and lv.index == before
