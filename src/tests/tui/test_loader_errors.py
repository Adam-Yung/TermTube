"""Every list loader against every typed source error and a raw exception with markup-looking text."""

from unittest.mock import MagicMock

import pytest

from src.errors import ExtractionFailed, NetworkDown, RateLimited, SignInRequired
from src.tests.fakes import silence_detail_workers, silence_empty_feed_modal
from src.tests.tui.waits import settle
from src.tui.widgets.video_list import VideoListPanel

RAW = "boom [x] [/y] \\"
ERRORS = [
    (SignInRequired("x"), "sign-in"),
    (RateLimited("x"), "rate limiting"),
    (NetworkDown("x"), "Network error"),
    (ExtractionFailed("x"), "YouTube changed"),
    (RuntimeError(RAW), RAW),
]
ENTRIES = [{"id": f"vid{i:08d}", "title": f"Video {i}", "uploader": "Chan", "duration": 60} for i in range(1, 4)]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, temp_history):
    silence_detail_workers(monkeypatch)
    silence_empty_feed_modal(monkeypatch)
    monkeypatch.setattr("src.tui.screens.mixins.feed_loader.resolve_browser", lambda cfg: "chrome")
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: ENTRIES)


def raiser(exc):
    return MagicMock(side_effect=exc)


def message(screen) -> str:
    panel = screen.query_one(VideoListPanel)
    return str(panel._message.content) if panel._message.display else ""


def patch_view(monkeypatch, view, fn):
    """Make the fetch behind ``view`` call ``fn``."""
    if view == "subscriptions":
        monkeypatch.setattr("src.ytdlp.fetch_subscribed_channels", fn)
    elif view == "search":
        monkeypatch.setattr("src.ytdlp.fetch_search_batch", fn)
    elif view == "library":
        monkeypatch.setattr("src.library.all_entries", fn)
    elif view == "history":
        monkeypatch.setattr("src.history.all_entries", fn)
    else:
        monkeypatch.setattr("src.ytdlp.fetch_page_batch", fn)


VIEWS = ["home", "subscriptions", "history:yt", "history:wl", "search", "library", "history"]


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("exc, shown", ERRORS, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None)
async def test_a_failing_load_shows_a_message_and_recovers(app, monkeypatch, view, exc, shown):
    prompts = []
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._prompt_ytdlp_update", lambda *a: prompts.append(a))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        screen._search.push("cats")
        patch_view(monkeypatch, view, raiser(exc))
        prompts.clear()
        screen._load_view(view)
        await settle(app, pilot)
        text = message(screen)
        extraction = isinstance(exc, ExtractionFailed)
        if extraction and view == "home":
            assert prompts and screen._active_workers == 0
        else:
            assert not prompts
            assert shown in text.replace("\\[", "[").replace("\u200b", "")
        assert screen._active_workers == 0
        patch_view(monkeypatch, view, lambda *a, **k: list(ENTRIES))
        screen._load_view(view)
        await settle(app, pilot)
        assert not message(screen) or "Nothing" in message(screen)
        assert screen._active_workers == 0


CHANNEL_URL = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"


@pytest.mark.parametrize("kind", ["videos", "playlists", "shorts", "live", "playlist"])
@pytest.mark.parametrize("exc, shown", ERRORS, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None)
async def test_channel_loaders_show_the_message_and_recover(app, monkeypatch, kind, exc, shown):
    from src import innertube
    from src.tui.screens.channel_screen import ChannelScreen

    page = innertube.ChannelPage(list(ENTRIES))
    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    for name in ("fetch_channel_page", "fetch_channel_playlists", "fetch_playlist_page"):
        monkeypatch.setattr(f"src.innertube.{name}", raiser(exc))
    monkeypatch.setattr("src.ytdlp.fetch_channel_videos", raiser(exc))
    monkeypatch.setattr("src.ytdlp.fetch_channel_playlists", raiser(exc))
    async with app.run_test(size=(110, 34)) as pilot:
        await settle(app, pilot)
        app.push_screen(ChannelScreen(CHANNEL_URL, "Rick"))
        await settle(app, pilot)
        screen = app.screen
        if kind == "playlist":
            screen._activate_entry({"_is_playlist": True, "id": "PL1", "title": "T"})
        elif kind != "videos":
            screen._current_tab = f"ch-tab-{kind}"
            screen._start_content_load()
        await settle(app, pilot)
        # The channel page shows the typed message only; a raw exception reads as an extraction failure.
        assert (ExtractionFailed.message if shown == RAW else shown) in message(screen)
        monkeypatch.setattr("src.innertube.fetch_channel_page", lambda *a, **k: page)
        monkeypatch.setattr("src.innertube.fetch_playlist_page", lambda *a, **k: page)
        monkeypatch.setattr("src.innertube.fetch_channel_playlists", lambda *a, **k: list(ENTRIES))
        screen._start_content_load()
        await settle(app, pilot)
        assert not message(screen)


def plain_text(markup: str) -> str:
    from textual.content import Content

    return Content.from_markup(markup).plain.replace("​", "")


@pytest.mark.parametrize("exc, shown", ERRORS, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None)
async def test_a_failing_detail_fetch_clears_the_spinner_and_keeps_the_list(app, monkeypatch, exc, shown):
    monkeypatch.setattr("src.ytdlp.fetch_page_batch", lambda *a, **k: list(ENTRIES))
    monkeypatch.setattr("src.streams.prefetch_stream_url", raiser(exc))
    monkeypatch.setattr("src.innertube.fetch_video_details", raiser(exc))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        screen = app.screen
        entry = ENTRIES[0]
        screen._detail_worker(entry["id"], entry, screen._focus_session)
        await settle(app, pilot)
        assert screen._active_workers == 0 and not message(screen)


@pytest.mark.parametrize("exc, shown", ERRORS, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None)
async def test_a_failing_stream_resolve_notifies_once_and_stops(app, monkeypatch, exc, shown):
    import asyncio

    told, logged = [], []
    controller = None
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        controller = app.audio
        controller._session = 1
        app.config._data["sponsorblock"] = {"enabled": False}
        monkeypatch.setattr(type(app), "notify", lambda self, msg, **kw: told.append(msg))
        monkeypatch.setattr(controller, "log", logged.append)
        monkeypatch.setattr("src.streams.resolve_for_playback", raiser(exc))
        await asyncio.to_thread(controller._launch_worker, {"id": "AAAAAAAAAAA", "title": "t"}, 1, "")
        await pilot.pause()
        assert len(told) == 1 and plain_text(told[0]).startswith(
            exc.message if hasattr(exc, "message") else f"Audio failed to start: {RAW}"
        )
        assert logged and plain_text(logged[0])


@pytest.mark.parametrize("exc, shown", ERRORS, ids=lambda v: type(v).__name__ if isinstance(v, Exception) else None)
async def test_a_failing_download_shows_the_error_text(app, monkeypatch, exc, shown):
    from src.tui.screens.download_modal import DownloadModal

    monkeypatch.setattr("src.downloads.download_video_with_progress", raiser(exc))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        app.push_screen(DownloadModal("AAAAAAAAAAA", {"title": "t"}), lambda ok: None)
        await settle(app, pilot)
        status = str(app.screen.query_one("#download-status").content)
        assert "Download failed" in str(app.screen.query_one("#download-title").content)
        assert plain_text(status).strip() and "x" in status or RAW.split()[0] in plain_text(status)


async def test_a_failing_suggestion_fetch_leaves_the_search_box_usable(app, monkeypatch):
    from src.tui.screens.search_modal import SearchModal

    monkeypatch.setattr("src.innertube.fetch_suggestions", raiser(NetworkDown("x")))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        results = []
        app.push_screen(SearchModal(), results.append)
        await pilot.pause()
        for ch in "cats":
            await pilot.press(ch)
        modal = app.screen
        for _ in range(3):
            await modal.workers.wait_for_complete() if modal.workers else None
            await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause()
    assert results == ["cats"]


async def test_the_stream_prefetch_calls_a_function_that_exists(app, monkeypatch):
    calls = []
    monkeypatch.setattr("src.streams.prefetch_stream_url", lambda vid, config, **kw: calls.append(vid))
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(app, pilot)
        app.screen._prefetch_stream_worker("AAAAAAAAAAA")
        await settle(app, pilot)
    assert calls and set(calls) == {"AAAAAAAAAAA"}
