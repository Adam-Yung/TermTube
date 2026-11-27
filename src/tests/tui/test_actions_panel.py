"""The Actions panel lists only what applies to the current tab, focus and row."""

from textual.widgets import Tabs

from src import playlist
from src.tests.tui.test_screen_layout_audit import fake_data, main_app  # noqa: F401  (fixtures)


def keys(screen):
    return {key for key, _ in screen.panel_hints()}


async def open_tab(app, pilot, tab):
    app.screen.query_one("#nav-tabs", Tabs).active = tab
    await pilot.pause(0.6)


async def test_home_lists_row_actions_and_the_played_toggle_only(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        got = keys(main_app.screen)
        assert {"⏎", "v", "a", "d", "c", "y", "p", "b", "f", "Z"} <= got
        assert not got & {"m", "D", "u", "Y", "s", "t", "n", "R", "J K", "P", "S", "E"}


async def test_history_adds_marks_removal_and_source(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await open_tab(main_app, pilot, "history")
        got = keys(main_app.screen)
        assert {"m", "D", "s"} <= got and "Y" not in got and not got & {"Z", "t", "n"}


async def test_search_adds_sort_and_type(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        main_app.screen._show_search_results("alpha")
        await pilot.pause(0.6)
        got = keys(main_app.screen)
        assert {"s", "t", "f"} <= got and not got & {"m", "D", "Z"}


async def test_playlist_rows_have_play_actions_and_channel_rows_none(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.6)
        screen = main_app.screen
        for entry, enter, plays in (({"id": "PLx", "title": "A list", "_is_playlist": True}, "Open playlist",
                                      {"v", "a", "e"}),
                                     ({"id": "UCx", "title": "A channel", "_is_channel": True}, "Open channel",
                                      set())):
            screen._selected_entry = lambda entry=entry: entry
            hints = dict(screen.panel_hints())
            assert hints.get("⏎") == enter
            assert set(hints) & {"v", "a", "e", "d", "p"} == plays and {"y", "b"} <= set(hints)


async def test_library_collection_and_playlist_tools(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await open_tab(main_app, pilot, "library")
        screen = main_app.screen
        got = keys(screen)
        assert {"m", "D", "n"} <= got and not got & {"R", "J K", "P", "S", "E", "Y"}
        screen._select_collection(f"playlist:{playlist.list_playlists()[0]['id']}")
        await pilot.pause(0.6)
        assert {"R", "J K", "P", "S", "E", "D", "n"} <= keys(screen)


async def test_rail_focus_shows_rail_tools_and_follows_the_cursor(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await open_tab(main_app, pilot, "library")
        screen = main_app.screen
        await pilot.press("tab")
        await pilot.pause(0.3)
        assert dict(screen.panel_hints()).get("⏎") == "Open"
        got = keys(screen)
        assert "n" in got and not got & {"v", "a", "f", "R", "D"}
        await pilot.press("j", "j", "j")
        await pilot.pause(0.3)
        assert {"R", "D", "P", "S", "E"} <= keys(screen)
        assert ("R", "Rename") in screen.query_one("ActionBar")._action_entries()


async def test_undo_appears_after_a_removal(main_app):  # noqa: F811
    async with main_app.run_test(size=(120, 40)) as pilot:
        await open_tab(main_app, pilot, "history")
        screen = main_app.screen
        assert "u" not in keys(screen)
        await pilot.press("D", "y")
        await pilot.pause(0.5)
        assert "u" in keys(screen)
