"""Parsers must only emit keys declared in src/entries.py, so the row types stay true."""

import json
from pathlib import Path
from unittest.mock import patch

from src import feeds, innertube
from src.entries import ChannelEntry, LibraryEntry, PlaylistEntry, VideoEntry

FIXTURES = Path(__file__).parent.parent / "fixtures"


def keys(td) -> set[str]:
    return set(td.__annotations__)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_row_types_extend_the_shared_base():
    for kind in (VideoEntry, ChannelEntry, PlaylistEntry, LibraryEntry):
        assert {"id", "title", "thumbnail", "_is_playlist", "_is_channel"} <= keys(kind)
    assert keys(VideoEntry) < keys(LibraryEntry)


def test_search_rows_fit_video_entry():
    with patch.object(innertube, "_post_json", return_value=load("innertube_search.json")):
        rows = innertube.search_videos("x", count=3)
    assert rows and all(set(r) <= keys(VideoEntry) for r in rows)


def test_atom_rows_fit_video_entry():
    rows = feeds.parse_atom((FIXTURES / "channel_feed.xml").read_bytes())
    assert rows and all(set(r) <= keys(VideoEntry) for r in rows)


def test_channel_video_row_fits_video_entry():
    item = {"richItemRenderer": {"content": {"lockupViewModel": {"contentId": "AAAAAAAAAAA", "metadata": {}}}}}
    row = innertube._parse_channel_video_item(item)
    assert row and set(row) <= keys(VideoEntry)


def test_playlist_rows_fit_playlist_entry():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlists.json")):
        rows = innertube.fetch_channel_playlists("UCx", count=3)
    assert rows and all(set(r) <= keys(PlaylistEntry) for r in rows)
