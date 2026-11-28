"""Enter menu and Actions panel are built from ``keymap.ROW_ACTIONS``; the panel repeats no footer key and fits."""

import pytest

from src.tui import keymap
from src.tui.screens.video_action_modal import VideoActionModal

ENTRY = {"id": "abc123def45", "title": "A video", "uploader": "Chan", "channel_id": "UC1"}


def test_every_row_action_has_a_key_and_a_screen_action():
    from src.tui.screens.main_screen import MainScreen

    for row in keymap.ROW_ACTIONS:
        assert keymap.key_of(row.action)
        assert callable(getattr(MainScreen, f"action_{row.action}"))


async def test_menu_lists_each_row_action_with_its_bound_key(quiet_app):
    async with quiet_app.run_test(size=(100, 30)) as pilot:
        quiet_app.push_screen(VideoActionModal(ENTRY))
        await pilot.pause(0.2)
        rows = [str(item.query_one("Static").content) for item in quiet_app.screen.query("ListItem")]
    assert len(rows) == len(keymap.ROW_ACTIONS)
    for row, text in zip(keymap.ROW_ACTIONS, rows, strict=True):
        assert f"({keymap.key_of(row.action)})" in text and row.label in text


async def test_menu_leaves_out_what_does_not_apply_to_the_row(quiet_app):
    async with quiet_app.run_test(size=(100, 30)):
        screen = quiet_app.screen
        assert screen._hidden_menu_actions(ENTRY) == set()
        assert screen._hidden_menu_actions({**ENTRY, "is_live": True}) == {"download"}
        assert screen._hidden_menu_actions({**ENTRY, "_has_audio": True}) == {"download"}
        gone = screen._hidden_menu_actions({**ENTRY, "_missing_file": True})
        assert {"watch", "audio", "audio_enqueue", "download", "playlist"} <= gone
        assert not {"channel", "copy_url", "browser"} & gone


@pytest.mark.parametrize("size", [(100, 30), (120, 40), (160, 50)])
async def test_actions_panel_repeats_no_footer_key_and_fits(quiet_app, size):
    async with quiet_app.run_test(size=size) as pilot:
        await pilot.pause(0.3)
        screen = quiet_app.screen
        bar = screen.query_one("ActionBar")
        keys = {key for key, _ in bar._action_entries()}
        footer = {v.binding.key for v in screen.active_bindings.values() if v.binding.show}
        assert not keys & footer
        grid = bar.query_one("#ab-actions")
        assert grid.region.bottom <= bar.content_region.bottom
        assert bar.region.bottom <= screen.query_one("DetailPanel").region.bottom
