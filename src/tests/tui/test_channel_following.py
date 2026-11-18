"""Local channel bookmarks: B on the channel page, F on the Subscriptions tab."""

from unittest.mock import patch

import pytest
from textual.worker import WorkerCancelled

from src import channel_bookmarks
from src.tui.screens.channel_screen import ChannelScreen

A = "UCuAXFkgsw1L7xaCfnd5JJOw"
URL = f"https://www.youtube.com/channel/{A}"


def followed(channel_id):
    return any(e["id"] == channel_id for e in channel_bookmarks.entries())


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_channels):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._focus_channel", lambda *a: None)
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_start_content_once", lambda self: None)
    monkeypatch.setattr(ChannelScreen, "_load_content", lambda self, *a: None)


async def settle(app, pilot):
    for _ in range(3):
        try:
            await app.workers.wait_for_complete()
        except WorkerCancelled:
            pass
        await pilot.pause()


async def test_b_on_the_channel_page_follows_and_unfollows(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen(URL, "Rick"))
        await pilot.pause()
        screen = app.screen
        screen._info_panel().update_info({"channel": "Rick", "channel_id": A, "thumbnail": "https://yt3/a.jpg"})
        with patch.object(screen, "notify") as notify:
            await pilot.press("B")
            assert followed(A) and "Following Rick" in notify.call_args.args[0]
            assert channel_bookmarks.entries()[0]["thumbnail"] == "https://yt3/a.jpg"
            await pilot.press("B")
            assert not followed(A) and "Unfollowed" in notify.call_args.args[0]


async def test_b_before_the_channel_id_is_known_says_so(app):
    async with app.run_test(size=(110, 34)) as pilot:
        app.push_screen(ChannelScreen("https://www.youtube.com/@handle", "H"))
        await pilot.pause()
        with patch.object(app.screen, "_hint") as hint:
            await pilot.press("B")
        assert "still loading" in hint.call_args.args[0] and channel_bookmarks.entries() == []


async def test_f_on_subscriptions_lists_followed_channels_and_back_returns(app, monkeypatch):
    import src.ytdlp as ytdlp

    sub = {"id": "UCsub", "title": "Subbed", "_is_channel": True}
    monkeypatch.setattr(ytdlp, "fetch_subscribed_channels", lambda *a: [sub])
    channel_bookmarks.toggle(A, "Rick", "https://yt3/a.jpg")
    async with app.run_test(size=(110, 34)) as pilot:
        main = app.screen
        main.action_goto_tab("subscriptions")
        await settle(app, pilot)
        panel = main._list()
        assert [e["id"] for e in panel.visited_entries()] == ["UCsub"]
        await pilot.press("F")
        await settle(app, pilot)
        assert [e["id"] for e in panel.visited_entries()] == [A] and main._current_tab == "following"
        await pilot.press("escape")
        await settle(app, pilot)
        assert main._current_tab == "subscriptions" and [e["id"] for e in panel.visited_entries()] == ["UCsub"]


async def test_enter_on_a_followed_channel_opens_its_page_and_it_works_without_subscriptions(app, monkeypatch):
    import src.ytdlp as ytdlp

    monkeypatch.setattr(ytdlp, "fetch_subscribed_channels", lambda *a: [])
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)
    channel_bookmarks.toggle(A, "Rick")
    async with app.run_test(size=(110, 34)) as pilot:
        main = app.screen
        main.action_goto_tab("subscriptions")
        await settle(app, pilot)
        await pilot.press("F")
        await settle(app, pilot)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ChannelScreen) and app.screen._channel_url.endswith(A)
        assert app.screen._crumbs() == ["Subscriptions", "Rick"] or app.screen._crumbs()[-1] == "Rick"


async def test_f_elsewhere_says_to_open_subscriptions_and_an_empty_list_says_how_to_follow(app, monkeypatch):
    import src.ytdlp as ytdlp

    monkeypatch.setattr(ytdlp, "fetch_subscribed_channels", lambda *a: [])
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)
    async with app.run_test(size=(110, 34)) as pilot:
        main = app.screen
        with patch.object(main, "_hint") as hint:
            await pilot.press("F")
        assert "Subscriptions" in hint.call_args.args[0] and main._current_tab != "following"
        main.action_goto_tab("subscriptions")
        await settle(app, pilot)
        await pilot.press("F")
        await settle(app, pilot)
        assert "Press B" in str(main._list().query_one("#list-breadcrumb").content)
