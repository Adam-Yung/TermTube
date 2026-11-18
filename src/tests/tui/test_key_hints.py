"""Keys that cannot act say why, once; other keys still work (docs/plans/2026-11-15-key-conflicts-PLAN.md)."""

from unittest.mock import patch

import pytest

from src.tui.screens.mixins import item_actions

VIDEO = {"id": "AAAAAAAAAAA", "title": "t"}
OTHER = {"id": "BBBBBBBBBBB", "title": "o"}


async def hints_for(app, pilot, entry, action, *, playing=None):
    screen = app.screen
    screen._selected_entry = lambda: entry
    if playing:
        app.audio._play_pending = True
        app.audio._entry = playing
    with patch.object(screen, "notify") as notify:
        getattr(screen, action)()
        await pilot.pause(0.1)
    return [call.args[0] for call in notify.call_args_list]


async def test_pressing_a_on_the_playing_track_is_a_hint_not_a_restart(app):
    async with app.run_test(size=(100, 30)) as pilot:
        with patch.object(app.audio, "play_audio") as play:
            messages = await hints_for(app, pilot, VIDEO, "action_audio", playing=VIDEO)
            assert messages == ["Already playing this track."] and not play.called
            messages = await hints_for(app, pilot, OTHER, "action_audio", playing=VIDEO)
            assert messages == [] and play.called


async def test_transport_keys_say_nothing_is_playing(app):
    async with app.run_test(size=(100, 30)) as pilot:
        for action in ("action_audio_pause", "action_audio_stop", "action_audio_skip"):
            app.screen.__dict__.pop("_hint_times", None)
            assert await hints_for(app, pilot, VIDEO, action) == ["Nothing playing."]


async def test_skip_with_an_empty_queue_says_so_and_skip_with_a_queue_works(app):
    async with app.run_test(size=(100, 30)) as pilot:
        assert await hints_for(app, pilot, VIDEO, "action_audio_skip", playing=VIDEO) == ["Queue is empty."]
        app.audio._queue.append(OTHER)
        with patch.object(app.audio, "skip_audio") as skip:
            await hints_for(app, pilot, VIDEO, "action_audio_skip", playing=VIDEO)
        assert skip.called


async def test_the_same_hint_is_not_repeated_within_two_seconds(app):
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._selected_entry = lambda: VIDEO
        with patch.object(screen, "notify") as notify:
            for _ in range(5):
                screen.action_audio_stop()
            clock = [item_actions.time.monotonic() + 3]
            with patch.object(item_actions.time, "monotonic", lambda: clock[0]):
                screen.action_audio_stop()
            await pilot.pause(0.1)
        assert notify.call_count == 2


@pytest.mark.parametrize("entry", [
    {"id": "UCx", "title": "Chan", "_is_channel": True},
    {"id": "PLx", "title": "List", "_is_playlist": True},
])
async def test_video_keys_on_channel_and_playlist_rows_say_not_a_video(app, entry):
    async with app.run_test(size=(100, 30)) as pilot:
        for action in ("action_watch", "action_audio", "action_audio_enqueue", "action_download", "action_playlist"):
            app.screen.__dict__.pop("_hint_times", None)
            assert await hints_for(app, pilot, entry, action) == ["Not a video."], action


async def test_download_is_refused_for_live_streams_and_fully_local_videos(app):
    async with app.run_test(size=(100, 30)) as pilot:
        live = await hints_for(app, pilot, {**VIDEO, "is_live": True}, "action_download")
        assert live == ["Live stream: cannot download."]
        app.screen.__dict__.pop("_hint_times", None)
        both = await hints_for(app, pilot, {**VIDEO, "_local_type": "video", "_has_audio": True}, "action_download")
        assert both == ["Already downloaded as video and audio."]
        app.screen.__dict__.pop("_hint_times", None)
        with patch.object(app, "push_screen") as push:
            only_video = await hints_for(app, pilot, {**VIDEO, "_local_type": "video"}, "action_download")
        assert only_video == [] and push.called


def test_page_url_for_each_row_kind():
    page = item_actions._page_url
    assert page(VIDEO) == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    assert page({"_is_channel": True, "channel_url": "https://www.youtube.com/channel/UCx"}).endswith("/UCx")
    assert page({"_is_playlist": True, "url": "https://www.youtube.com/playlist?list=PLx"}).endswith("list=PLx")
    assert page({"_is_playlist": True, "id": "__playlist__mine"}) == ""
    assert page({"id": "__placeholder__"}) == "" and page(None) == ""


async def test_channel_page_hints_for_c_and_sort_on_playlists(app):
    from types import SimpleNamespace

    from src.tui.screens.channel_screen import ChannelScreen

    seen = []
    host = SimpleNamespace(
        _hint=lambda message, severity="warning": seen.append(message), _tab_kind=lambda: "playlists"
    )
    ChannelScreen.action_channel(host)
    ChannelScreen.action_sort(host)
    assert seen == ["Already on this channel.", "Playlists have no sort."]
