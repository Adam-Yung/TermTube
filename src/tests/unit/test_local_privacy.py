"""A local file's id never reaches YouTube, SponsorBlock or a thumbnail host, whichever path asks."""

from unittest.mock import patch

import pytest

from src import history, innertube, sponsorblock, streams
from src.ui import thumbnail

LOCAL = {"id": "local-0123456789abcdef0123", "title": "home video.mp4", "_local_path": "/x/home video.mp4",
         "_local_type": "video", "thumbnail": "https://i.ytimg.com/vi/x/mqdefault.jpg"}


def refuse(*args, **kwargs):
    pytest.fail("a local file reached the network layer")


def test_stream_resolution_refuses_local_ids():
    with patch("yt_dlp.YoutubeDL", side_effect=refuse):
        assert streams.resolve_stream_url(LOCAL["id"], None) is None


def test_innertube_details_refuse_local_ids():
    with patch.object(innertube, "_post_json", side_effect=refuse):
        assert innertube.fetch_video_details(LOCAL["id"]) is None


def test_sponsorblock_refuses_local_ids():
    with patch.object(sponsorblock, "_request", side_effect=refuse):
        assert sponsorblock.fetch_segments(LOCAL["id"]) == []


def test_thumbnail_download_refuses_local_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "THUMB_DIR", tmp_path)
    monkeypatch.setattr("src.local_media.thumbnail", lambda entry, dest: None)
    with patch("src.thumbnail_http.download_thumbnail", side_effect=refuse):
        assert thumbnail.ensure_thumb_jpeg(LOCAL["id"], LOCAL) is None
        assert thumbnail.download(LOCAL["id"], LOCAL["thumbnail"]) is None


def test_history_and_playlist_records_keep_the_path_of_local_files_only():
    record = history.slim(LOCAL, LOCAL["id"])
    assert record["_local_path"] == "/x/home video.mp4" and record["_local_type"] == "video"
    youtube = history.slim({**LOCAL, "id": "dQw4w9WgXcQ"}, "dQw4w9WgXcQ")
    assert "_local_path" not in youtube
