"""Every main-screen tab and the channel screen keep the layout rules at the sizes in ``layout_harness``."""

from functools import partial

import pytest
from textual.widgets import Tabs

from src import channel_bookmarks, playlist
from src.innertube import ChannelPage
from src.tests.tui.layout_data import LONG, long_entries
from src.tests.tui.layout_harness import MAIN_SIZES, ScreenScenario, audit_screen_scenario, settle
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.screens.queue_screen import QueueScreen


async def _tab(app, pilot, tab):
    app.screen.query_one("#nav-tabs", Tabs).active = tab
    await pilot.pause(0.6)


async def _view(app, pilot, *, tab, view):
    await _tab(app, pilot, tab)
    if tab == "library":
        app.screen._select_collection(view)
    await pilot.pause(0.6)


def _tab_scenario(name, tab):
    return ScreenScenario(name, partial(_tab, tab=tab))


def _view_scenario(name, tab, view):
    return ScreenScenario(name, partial(_view, tab=tab, view=view))


async def _search(app, pilot):
    app.screen._show_search_results("alpha")
    await pilot.pause(0.6)


async def _history_source(app, pilot):
    await _tab(app, pilot, "history")
    app.screen._select_collection("history:yt")
    await pilot.pause(0.6)


async def _following(app, pilot):
    for i in range(25):
        channel_bookmarks.toggle(f"UC{i:022d}", f"Followed channel number {i}")
    await _tab(app, pilot, "subscriptions")
    app.screen._select_collection("following")
    await pilot.pause(0.6)


async def _playlist(app, pilot):
    await _tab(app, pilot, "library")
    app.screen._select_collection(f"playlist:{playlist.list_playlists()[0]['id']}")
    await pilot.pause(0.6)


async def _empty_following(app, pilot):
    await _tab(app, pilot, "subscriptions")
    app.screen._select_collection("following")
    await pilot.pause(0.6)


async def _many_playlists(app, pilot):
    for i in range(40):
        playlist.create(f"Another playlist number {i}", long_entries(2))
    await _tab(app, pilot, "library")
    await pilot.pause(0.4)


async def _home(app, pilot):
    await pilot.pause(0.6)


MAIN_SCENARIOS = [
    ScreenScenario("home", _home),
    _tab_scenario("subscriptions", "subscriptions"),
    ScreenScenario("following", _following),
    ScreenScenario("following-empty", _empty_following),
    ScreenScenario("search", _search),
    _tab_scenario("history", "history"),
    ScreenScenario("history-source", _history_source),
    _tab_scenario("library", "library"),
    _view_scenario("library-videos", "library", "library:video"),
    _view_scenario("library-audio", "library", "library:audio"),
    ScreenScenario("library-playlist", _playlist),
    ScreenScenario("library-many-playlists", _many_playlists),
]


@pytest.mark.parametrize("scenario", MAIN_SCENARIOS, ids=lambda s: s.name)
async def test_main_screen_layout(main_app, scenario):
    async with main_app.run_test(size=MAIN_SIZES[-1]) as pilot:
        await pilot.pause(0.6)
        problems = await audit_screen_scenario(
            main_app, pilot, scenario, MAIN_SIZES, list_id="#video-list-panel", detail_id="#detail-panel", rail=True
        )
    assert not problems, "\n".join(problems)


CHANNEL_URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
LONG_DESC = "\n".join(f"Description line {n} " + "word " * 30 for n in range(1, 12))


async def _show_channel(app, pilot, *, tab, expand, entries):
    screen = app.screen
    screen._info_panel().update_info(
        {"channel": "A Channel With A Long Name Indeed", "description": LONG_DESC, "video_count": 442,
         "subscriber_count": 1234567, "channel_url": CHANNEL_URL, "joined": "Joined Mar 3, 2011"}
    )
    if tab:
        screen.query_one("#ch-tabs", Tabs).active = tab
        await settle(pilot, partial(_tab_problems, screen, tab))
    screen._show_first_page(screen._content_session, ChannelPage(entries or long_entries(30)))
    if expand:
        await pilot.press("i")
    await pilot.pause(0.5)


def _tab_problems(screen, tab) -> list[str]:
    return [] if screen._current_tab == tab else ["tab"]


def _pushed_problems(app, screen_class) -> list[str]:
    return [] if isinstance(app.screen, screen_class) else ["not pushed"]


def _channel_scenario(name, tab=None, *, expand=False, entries=None):
    return ScreenScenario(name, partial(_show_channel, tab=tab, expand=expand, entries=entries))


CHANNEL_SCENARIOS = [
    _channel_scenario("channel-videos"),
    _channel_scenario("channel-videos-expanded", expand=True),
    _channel_scenario("channel-playlists", "ch-tab-playlists",
                      entries=[{"id": f"PL{i}", "title": f"Playlist {LONG} {i}", "_is_playlist": True,
                                "video_count": 12} for i in range(20)]),
    _channel_scenario("channel-shorts", "ch-tab-shorts"),
    _channel_scenario("channel-live", "ch-tab-live"),
]


@pytest.mark.parametrize("scenario", CHANNEL_SCENARIOS, ids=lambda s: s.name)
async def test_channel_screen_layout(main_app, scenario, monkeypatch):
    for name in ("_load_channel_info", "_start_content_once", "_start_content_load"):
        monkeypatch.setattr(ChannelScreen, name, lambda self: None)
    async with main_app.run_test(size=MAIN_SIZES[-1]) as pilot:
        main_app.push_screen(ChannelScreen(CHANNEL_URL, "Chan"))
        await settle(pilot, partial(_pushed_problems, main_app, ChannelScreen))
        problems = await audit_screen_scenario(
            main_app, pilot, scenario, MAIN_SIZES, list_id="#ch-video-list", detail_id="#ch-detail-panel"
        )
    assert not problems, "\n".join(problems)


async def _show_playlist(app, pilot, *, header):
    screen = app.screen
    screen._show_first_page(screen._content_session, ChannelPage(long_entries(30), "tok", header))
    await pilot.pause(0.5)


def _playlist_scenario(name, *, info=None):
    header = {"playlist_id": "PLx", "title": "A Playlist With A Long Name Indeed " * 2, "description": LONG_DESC,
              "owner": "Some Owner", "owner_id": "UCx", "video_count": 442, "view_count": 1234567,
              "updated": "Updated 4 days ago", "thumbnail": ""} if info is None else info
    return ScreenScenario(name, partial(_show_playlist, header=header))


@pytest.mark.parametrize("scenario", [_playlist_scenario("playlist-page"),
                                      _playlist_scenario("playlist-page-no-header", info={})],
                         ids=lambda s: s.name)
async def test_playlist_page_layout(main_app, scenario, monkeypatch):
    for name in ("_start_content_once", "_start_content_load"):
        monkeypatch.setattr(ChannelScreen, name, lambda self: None)
    async with main_app.run_test(size=MAIN_SIZES[-1]) as pilot:
        main_app.push_screen(ChannelScreen("", "", trail=["Search"], playlist={"id": "PLx", "title": "Hits"}))
        await settle(pilot, partial(_pushed_problems, main_app, ChannelScreen))
        problems = await audit_screen_scenario(
            main_app, pilot, scenario, MAIN_SIZES, list_id="#ch-video-list", detail_id="#ch-detail-panel"
        )
    assert not problems, "\n".join(problems)


async def _show_queue(app, pilot, *, entries):
    audio = app.audio
    audio._play_pending, audio._entry, audio._queue = True, entries[0], list(entries[1:])
    app.screen._rebuild()
    await pilot.pause(0.5)


async def test_queue_page_layout(main_app, monkeypatch):
    entries = long_entries(60)
    async with main_app.run_test(size=MAIN_SIZES[-1]) as pilot:
        main_app.push_screen(QueueScreen())
        await settle(pilot, partial(_pushed_problems, main_app, QueueScreen))
        problems = await audit_screen_scenario(
            main_app, pilot, ScreenScenario("queue-page", partial(_show_queue, entries=entries)), MAIN_SIZES,
            list_id="#queue-video-list", detail_id="#queue-detail-panel",
        )
    assert not problems, "\n".join(problems)
