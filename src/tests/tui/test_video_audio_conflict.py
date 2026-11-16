"""Video is refused while background audio plays; the menu hides its entries."""

from unittest.mock import patch

from src.tui.screens.watch_modal import WatchModal

ENTRY = {"id": "AAAAAAAAAAA", "title": "t"}


def watch_modals(app):
    return [s for s in app.screen_stack if isinstance(s, WatchModal)]


async def test_v_and_V_do_nothing_but_hint_while_audio_plays(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._selected_entry = lambda: ENTRY
        app.audio._play_pending = True
        with patch.object(screen, "notify") as notify, patch.object(screen, "_pick_quality") as pick:
            screen.action_watch()
            screen.action_watch_quality()
            await pilot.pause(0.2)
        assert not watch_modals(app) and not pick.called
        assert notify.call_count == 2 and "x" in notify.call_args.args[0]


async def test_a_quality_pick_made_before_audio_started_is_also_refused(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        app.audio._play_pending = True
        with patch.object(screen, "notify"):
            screen._watch(ENTRY, "best")
            await pilot.pause(0.2)
        assert not watch_modals(app)


async def test_video_still_opens_when_no_audio_plays(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._selected_entry = lambda: ENTRY
        with patch.object(WatchModal, "on_mount"):
            screen.action_watch()
            await pilot.pause(0.2)
        assert len(watch_modals(app)) == 1


async def test_menu_hides_video_entries_only_while_audio_plays(app):
    async with app.run_test(size=(100, 30)):
        screen = app.screen
        assert not {"watch", "watch_quality"} & screen._hidden_menu_actions(ENTRY)
        app.audio._play_pending = True
        assert {"watch", "watch_quality"} <= screen._hidden_menu_actions(ENTRY)
