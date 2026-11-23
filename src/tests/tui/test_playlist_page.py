"""A playlist opened from Search or Home: the channel page in playlist mode (header left, videos middle, no tabs)."""

import pytest
from textual.widgets import Static

from src import innertube
from src.tui.screens.channel_screen import ChannelScreen
from src.tui.widgets.video_list import VideoListPanel

PL = {"id": "PLhits", "title": "Hits", "_playlist_name": "Hits", "_is_playlist": True, "uploader": "Hitsify"}
INFO = {
    "playlist_id": "PLhits", "title": "Lofi Hits", "description": "Chill beats.", "owner": "Hitsify",
    "owner_id": "UCnFrtWHPWzuvzMwwJLv9dnA", "video_count": 50, "view_count": 62909, "updated": "Updated 4 days ago",
    "thumbnail": "",
}


def vids(n):
    return [{"id": f"v{i:010d}", "title": f"Song {i}", "channel_id": "UCother0000000000000000"} for i in range(n)]


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a: None)


def serve(monkeypatch, page):
    calls = []

    def fake(playlist_id, token="", **_):
        calls.append((playlist_id, token))
        return page

    monkeypatch.setattr(innertube, "fetch_playlist_page", fake)
    return calls


async def settle(app, pilot):
    for _ in range(3):
        await app.workers.wait_for_complete()
        await pilot.pause(0.1)


def shown(screen, selector):
    return str(screen.query_one(selector, Static).content)


async def open_page(app, pilot, trail=("Search",)):
    app.push_screen(ChannelScreen("", "", trail=list(trail), playlist=PL))
    await pilot.pause()
    await settle(app, pilot)
    return app.screen


async def test_the_page_shows_the_playlist_header_and_its_videos(app, monkeypatch):
    calls = serve(monkeypatch, innertube.ChannelPage(vids(3), "", INFO))
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        assert calls == [("PLhits", "")]
        assert "Lofi Hits" in shown(screen, "#ch-name") and "by Hitsify" in shown(screen, "#ch-subs")
        stats = shown(screen, "#ch-stats")
        assert "50 videos" in stats and "62,909 views" in stats and "Updated 4 days ago" in stats
        assert "Chill beats." in shown(screen, "#ch-desc")
        assert [e["title"] for e in screen._list().visited_entries()] == ["Song 0", "Song 1", "Song 2"]
        assert "Playlist: Lofi Hits" in str(screen.query_one("#list-breadcrumb").content)
        assert not screen.query_one("#ch-tabs").display


async def test_escape_leaves_the_page_in_one_press(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2), "", INFO))
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen


async def test_tabs_sort_and_follow_answer_with_a_reason(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2), "", INFO))
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        for key in ("s", "B", "H", "L", "grave_accent"):
            await pilot.press(key)
            await pilot.pause()
            assert app.screen is screen
        assert screen._tool_actions() == {"filter", "play_all", "enqueue_all", "save_list"}


async def test_o_opens_the_owner_channel_and_c_the_channel_of_the_row(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2), "", INFO))
    import src.ytdlp as ytdlp

    monkeypatch.setattr(ChannelScreen, "_load_channel_info", lambda self: None)
    monkeypatch.setattr(innertube, "fetch_channel_page", lambda *a, **k: innertube.ChannelPage([]))
    monkeypatch.setattr(ytdlp, "fetch_channel_videos", lambda *a, **k: [])
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        await pilot.press("o")
        await pilot.pause()
        owner = app.screen
        assert owner is not screen and owner._channel_url.endswith("UCnFrtWHPWzuvzMwwJLv9dnA")
        assert owner._trail == ["Search", "Playlist: Lofi Hits"]
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert app.screen is not screen and app.screen._channel_url.endswith("UCother0000000000000000")


async def test_an_unavailable_playlist_shows_youtubes_reason(app, monkeypatch):
    info = {"playlist_id": "PLhits", "unavailable": "This playlist type is unviewable."}
    serve(monkeypatch, innertube.ChannelPage([], "", info))
    import src.ytdlp as ytdlp

    def no_ytdlp(*a, **k):
        raise AssertionError("yt-dlp must not repeat a reason YouTube already gave")

    monkeypatch.setattr(ytdlp, "fetch_page_batch", no_ytdlp)
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        assert "unviewable" in str(screen._list()._message.content)
        assert "Hits" in shown(screen, "#ch-name")


async def test_a_playlist_without_a_header_still_names_itself(app, monkeypatch):
    serve(monkeypatch, innertube.ChannelPage(vids(2)))
    async with app.run_test(size=(120, 36)) as pilot:
        screen = await open_page(app, pilot)
        assert "Hits" in shown(screen, "#ch-name")
        assert isinstance(screen._list(), VideoListPanel)


async def test_a_mix_row_is_read_through_next_and_says_it_has_no_end(app, monkeypatch):
    mix = {"id": "RDdQw4w9WgXcQ", "title": "Mix", "_is_playlist": True}
    info = {"playlist_id": mix["id"], "title": "Mix - Rick", "owner": "YouTube", "owner_id": "", "video_count": None,
            "view_count": None, "updated": "", "mix": True, "description": "", "thumbnail": ""}
    seen = []

    def fake_mix(playlist_id, token="", **_):
        seen.append(playlist_id)
        return innertube.ChannelPage(vids(3), "tok", info)

    def no_browse(*a, **k):
        raise AssertionError("a Mix is not a browse page")

    monkeypatch.setattr(innertube, "fetch_mix_page", fake_mix)
    monkeypatch.setattr(innertube, "fetch_playlist_page", no_browse)
    async with app.run_test(size=(120, 36)) as pilot:
        app.push_screen(ChannelScreen("", "", trail=["Home"], playlist=mix))
        await pilot.pause()
        await settle(app, pilot)
        screen = app.screen
        assert seen[0] == "RDdQw4w9WgXcQ" and "Mix - Rick" in shown(screen, "#ch-name")
        assert len(screen._list().visited_entries()) == 3
