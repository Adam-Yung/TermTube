"""Sort and channel-tab pickers take their colours from the active theme, like NavModal."""

import pytest

from src.tui.screens.channel_tab_modal import ChannelTabModal
from src.tui.screens.sort_modal import SortModal
from src.tui.widgets.action_bar import THEME_COLORS

TITLE_COLORS = {"crimson": "#ff4444", "amber": "#e8820c", "ocean": "#0ea5e9", "midnight": "#a855f7"}


@pytest.mark.parametrize("modal,title_id,dialog_id", [
    (SortModal, "#sort-title", "#sort-dialog"),
    (ChannelTabModal, "#ch-tab-title", "#ch-tab-dialog"),
])
async def test_title_border_and_numbers_follow_each_theme(app, modal, title_id, dialog_id):
    async with app.run_test(size=(100, 30)) as pilot:
        for theme, color in TITLE_COLORS.items():
            app.config._data["theme"] = theme
            for other in TITLE_COLORS:
                app.set_class(other == theme and other != "crimson", f"theme-{other}")
            app.push_screen(modal())
            await pilot.pause(0.2)
            screen = app.screen
            assert screen.query_one(title_id).styles.color.hex.lower() == color
            assert screen.query_one(dialog_id).styles.border.top[1].hex.lower() == color
            rows = screen.query(".nav-row")
            assert rows and THEME_COLORS[theme] in str(rows.first().content)
            app.pop_screen()
            await pilot.pause(0.1)
