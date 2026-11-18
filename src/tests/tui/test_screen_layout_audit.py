"""Every main-screen tab and the channel screen keep the layout rules at the sizes in ``layout_harness``."""

import json

import pytest
from textual.widgets import Tabs

from src import channel_bookmarks, history, playlist
from src.innertube import ChannelPage
from src.tests.tui.layout_harness import MAIN_SIZES, ScreenScenario, audit_screen_scenario
from src.tui.screens.channel_screen import ChannelScreen

LONG = "A rather long video title that goes on and on to test how a list row copes with a narrow column"


def _entries(count=40, **extra):
    return [
        {"id": f"vid{i:08d}", "title": f"{LONG} {i}", "uploader": "A Channel With A Long Name Indeed",
         "duration": 3700, "view_count": 1234567, "upload_date": "20250101", "description": "d " * 200, **extra}
        for i in range(count)
    ]


def _channels(count=30):
    return [{"id": f"UC{i:020d}", "title": f"Channel number {i}", "channel": f"Channel number {i}", "_is_channel": True,
             "subscriber_count": 123456, "video_count": 321, "channel_url": f"https://www.youtube.com/channel/UC{i}"}
            for i in range(count)]


@pytest.fixture
def fake_data(monkeypatch, tmp_path, temp_history, temp_channels, temp_playlists):
    """Fake feeds, history, library files and playlists; nothing leaves the process."""
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: _entries())
    monkeypatch.setattr("src.ytdlp.fetch_subscribed_channels", lambda *a, **k: _channels())
    monkeypatch.setattr("src.ytdlp.fetch_search_batch", lambda query, *a, count=50, **k: _entries(count))
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda config: "firefox")
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a, **k: None)
    for entry in _entries(12):
        history.add(entry)
    videos, audio = tmp_path / "vid", tmp_path / "aud"
    for directory, ext, kind in ((videos, "mp4", "v"), (audio, "mp3", "a")):
        directory.mkdir()
        for i in range(8):
            vid = f"{kind}{i:010d}"
            (directory / f"{vid}.{ext}").write_bytes(b"x" * 5)
            sidecar = {"id": vid, "title": f"{LONG} {vid}", "uploader": "Alpha", "duration": 100,
                       "upload_date": "20260101"}
            (directory / f"{vid}.info.json").write_text(json.dumps(sidecar), encoding="utf-8")
    monkeypatch.setitem  # noqa: B018  (config is set through the app below)
    return videos, audio


@pytest.fixture
def main_app(app, fake_data):
    videos, audio = fake_data
    app.config._data["video_dir"], app.config._data["audio_dir"] = str(videos), str(audio)
    for i in range(3):
        playlist.create(f"Playlist number {i}", _entries(4))
    return app


async def _tab(app, pilot, tab):
    app.screen.query_one("#nav-tabs", Tabs).active = tab
    await pilot.pause(0.6)


def _tab_scenario(name, tab):
    async def setup(app, pilot):
        await _tab(app, pilot, tab)

    return ScreenScenario(name, setup)


def _view_scenario(name, tab, view):
    async def setup(app, pilot):
        await _tab(app, pilot, tab)
        if tab == "library":
            app.screen._select_collection(view)
        await pilot.pause(0.6)

    return ScreenScenario(name, setup)


async def _search(app, pilot):
    app.screen._show_search_results("alpha")
    await pilot.pause(0.6)


async def _history_source(app, pilot):
    await _tab(app, pilot, "history")
    app.screen.action_history_source()
    await pilot.pause(0.6)


async def _following(app, pilot):
    for i in range(25):
        channel_bookmarks.toggle(f"UC{i:022d}", f"Followed channel number {i}")
    await _tab(app, pilot, "subscriptions")
    app.screen.action_following()
    await pilot.pause(0.6)


async def _playlist(app, pilot):
    await _tab(app, pilot, "library")
    app.screen._select_collection(f"playlist:{playlist.list_playlists()[0]['id']}")
    await pilot.pause(0.6)


async def _many_playlists(app, pilot):
    for i in range(40):
        playlist.create(f"Another playlist number {i}", _entries(2))
    await _tab(app, pilot, "library")
    await pilot.pause(0.4)


async def _home(app, pilot):
    await pilot.pause(0.6)


MAIN_SCENARIOS = [
    ScreenScenario("home", _home),
    _tab_scenario("subscriptions", "subscriptions"),
    ScreenScenario("following", _following),
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


def _channel_scenario(name, tab=None, *, expand=False, entries=None):
    async def setup(app, pilot):
        screen = app.screen
        screen._info_panel().update_info(
            {"channel": "A Channel With A Long Name Indeed", "description": LONG_DESC, "video_count": 442,
             "subscriber_count": 1234567, "channel_url": CHANNEL_URL, "joined": "Joined Mar 3, 2011"}
        )
        if tab:
            screen.query_one("#ch-tabs", Tabs).active = tab
            await pilot.pause(0.3)
        screen._show_first_page(screen._content_session, ChannelPage(entries or _entries(30)))
        if expand:
            await pilot.press("i")
        await pilot.pause(0.5)

    return ScreenScenario(name, setup)


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
        await pilot.pause(0.4)
        problems = await audit_screen_scenario(
            main_app, pilot, scenario, MAIN_SIZES, list_id="#ch-video-list", detail_id="#ch-detail-panel"
        )
    assert not problems, "\n".join(problems)
