"""Key-conflicts plan: channel page keys ? , / q, the relabelled menu entry, audio keys in the download modal."""

import threading
from functools import partial
from unittest.mock import patch

from src.strings import text
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.download_modal import DownloadModal
from src.tui.screens.help_screen import HelpScreen
from src.tui.screens.main_screen import MainScreen
from src.tui.screens.search_modal import SearchModal
from src.tui.screens.settings_modal import SettingsModal
from src.tui.screens.video_action_modal import VideoActionModal

ENTRY = {"id": "AAAAAAAAAAA", "title": "t"}


def names(app):
    return [type(s).__name__ for s in app.screen_stack]


async def open_channel(app, pilot):
    with patch.object(ChannelScreen, "_load_channel_info"), patch.object(ChannelScreen, "_start_content_once"):
        app.push_screen(ChannelScreen("https://www.youtube.com/channel/UCx", "Chan"))
        await pilot.pause(0.3)


async def test_question_mark_and_comma_open_help_and_settings_over_the_channel_page(app):
    async with app.run_test(size=(110, 34)) as pilot:
        await open_channel(app, pilot)
        await pilot.press("question_mark")
        await pilot.pause(0.3)
        assert isinstance(app.screen, HelpScreen) and "ChannelScreen" in names(app)
        await pilot.press("escape")
        await pilot.pause(0.2)
        await pilot.press("comma")
        await pilot.pause(0.3)
        assert isinstance(app.screen, SettingsModal) and "ChannelScreen" in names(app)


async def test_slash_leaves_the_channel_page_and_opens_search(app):
    async with app.run_test(size=(110, 34)) as pilot:
        await open_channel(app, pilot)
        await pilot.press("slash")
        await pilot.pause(0.4)
        assert isinstance(app.screen, SearchModal) and "ChannelScreen" not in names(app)


async def test_q_on_the_channel_page_opens_the_queue_and_q_returns(app):
    async with app.run_test(size=(110, 34)) as pilot:
        await open_channel(app, pilot)
        await pilot.press("q")
        await pilot.pause(0.3)
        assert names(app)[-2:] == ["ChannelScreen", "QueueScreen"]
        await pilot.press("q")
        await pilot.pause(0.3)
        assert names(app)[-1] == "ChannelScreen" and app.is_running


async def test_ctrl_q_on_the_channel_page_quits_through_the_main_screen(app):
    async with app.run_test(size=(110, 34)) as pilot:
        await open_channel(app, pilot)
        with patch.object(MainScreen, "action_quit_app") as quit_app:
            await pilot.press("ctrl+q")
            await pilot.pause(0.3)
        assert quit_app.called


async def test_menu_offers_queueing_when_idle_with_its_own_label_and_hides_it_for_the_playing_track(app):
    async with app.run_test(size=(110, 34)):
        screen = app.screen
        assert "audio_enqueue" not in screen._hidden_menu_actions(ENTRY)
        assert "queue more" in screen._menu_labels()["audio_enqueue"]
        app.audio._play_pending = True
        app.audio._entry = ENTRY
        assert "audio_enqueue" in screen._hidden_menu_actions(ENTRY)
        assert "audio_enqueue" not in screen._hidden_menu_actions({"id": "BBBBBBBBBBB"})
        assert screen._menu_labels() == {}


async def test_the_open_menu_shows_the_override_label(app):
    async with app.run_test(size=(110, 34)) as pilot:
        screen = app.screen
        screen._selected_entry = lambda: ENTRY
        screen.action_activate()
        await pilot.pause(0.4)
        assert isinstance(app.screen, VideoActionModal)
        labels = [str(w.content) for w in app.screen.query("#vaction-list Static")]
        assert any(text("item_actions.menu_play_audio") in label for label in labels)


def _blocked_download(release, video_id, config, *, cancel, **kwargs):
    release.wait(5)
    return False


async def test_space_and_x_reach_the_audio_during_a_download(app):
    release = threading.Event()

    async with app.run_test(size=(110, 34)) as pilot:
        with patch("src.downloads.download_video_with_progress", partial(_blocked_download, release)), \
                patch.object(app.audio, "toggle_audio_pause") as pause, patch.object(app.audio, "stop_audio") as stop:
            app.push_screen(DownloadModal(ENTRY["id"], ENTRY))
            await pilot.pause(0.3)
            assert isinstance(app.screen, DownloadModal)
            await pilot.press("space")
            await pilot.press("x")
            await pilot.pause(0.1)
            release.set()
        assert pause.called and stop.called
