"""A Home playlist row has no thumbnail or description from yt-dlp: focusing it reads them from the playlist header."""

from src import innertube
from src.tui.screens.mixins.detail_focus import _needs_playlist_header

ROW = {"id": "PLabcdefghij", "title": "Jazz", "_is_playlist": True, "_type": "playlist", "thumbnail": ""}


def test_which_rows_need_the_header():
    assert _needs_playlist_header(ROW)
    assert not _needs_playlist_header({**ROW, "id": "RDabcdefghijk"})  # a Mix row carries its first video's thumbnail
    assert not _needs_playlist_header({**ROW, "thumbnail": "u"})  # search and channel rows already have one
    assert not _needs_playlist_header({**ROW, "_header_read": True})
    assert not _needs_playlist_header({"id": "abcdefghijk", "title": "v"})


async def test_focusing_a_playlist_row_fills_its_thumbnail_and_description(app, monkeypatch):
    info = {"thumbnail": "https://i.ytimg.com/pl.jpg", "description": "Smooth tunes", "video_count": 12}
    monkeypatch.setattr(innertube, "fetch_playlist_page", lambda pid, token="": innertube.ChannelPage([], "", info))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.8)  # the fixture's own Home load settles first
        screen = app.screen
        panel = screen._list()
        panel.add_entries(2, [dict(ROW)])
        screen._focus_video(dict(ROW))
        await pilot.pause(0.8)
        merged = next(e for e in panel.visited_entries() if e["id"] == ROW["id"])
        assert merged["thumbnail"] == info["thumbnail"]
        assert merged["description"] == "Smooth tunes"
        assert merged["playlist_count"] == 12
