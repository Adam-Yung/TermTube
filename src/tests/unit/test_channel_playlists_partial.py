"""A channel's playlist listing is lazy: rows read before yt-dlp fails are still returned."""

import yt_dlp

from src import ytdlp


def failing_listing():
    yield {"_type": "url", "id": "PL1", "title": "One", "thumbnail": "t"}
    raise yt_dlp.utils.DownloadError("lost the connection")


class Listing:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return {"entries": failing_listing()}


def test_rows_read_before_a_failure_are_kept(monkeypatch):
    monkeypatch.setattr(ytdlp, "_make_ydl", lambda *a, **k: Listing())
    rows = ytdlp.fetch_channel_playlists("https://www.youtube.com/@x", None, None)
    assert [r["id"] for r in rows] == ["PL1"]
    assert rows[0]["_playlist_name"] == "One"
