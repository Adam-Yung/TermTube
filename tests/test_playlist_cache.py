"""Tests for playlist cache pinning/unpinning in cache.py."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))


@pytest.fixture
def temp_cache(tmp_path, monkeypatch):
    """Set up temporary cache directories and return a Cache instance."""
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbs"
    playlist_video_dir = tmp_path / "playlist_videos"
    playlist_thumb_dir = tmp_path / "playlist_thumbs"

    video_dir.mkdir()
    thumb_dir.mkdir()
    playlist_video_dir.mkdir()
    playlist_thumb_dir.mkdir()

    monkeypatch.setattr("src.cache.VIDEO_DIR", video_dir)
    monkeypatch.setattr("src.cache.THUMB_DIR", thumb_dir)
    monkeypatch.setattr("src.cache.PLAYLIST_VIDEO_DIR", playlist_video_dir)
    monkeypatch.setattr("src.cache.PLAYLIST_THUMB_DIR", playlist_thumb_dir)
    monkeypatch.setattr("src.cache.CACHE_DIR", tmp_path)

    from src.cache import Cache
    cache = Cache({"metadata": 86400})
    return cache, video_dir, thumb_dir, playlist_video_dir, playlist_thumb_dir


class TestPinVideo:
    def test_pin_from_main_cache(self, temp_cache):
        cache, video_dir, _, playlist_video_dir, _ = temp_cache
        entry = {"id": "abc123", "title": "Test Video", "_cached_at": time.time()}
        (video_dir / "abc123.json").write_text(json.dumps(entry))

        cache.pin_video("abc123")

        pinned = json.loads((playlist_video_dir / "abc123.json").read_text())
        assert pinned["title"] == "Test Video"

    def test_pin_with_provided_entry(self, temp_cache):
        cache, _, _, playlist_video_dir, _ = temp_cache
        entry = {"id": "xyz789", "title": "Provided", "_cached_at": time.time()}

        cache.pin_video("xyz789", entry)

        pinned = json.loads((playlist_video_dir / "xyz789.json").read_text())
        assert pinned["title"] == "Provided"

    def test_pin_no_op_when_not_in_cache(self, temp_cache):
        cache, _, _, playlist_video_dir, _ = temp_cache
        cache.pin_video("nonexistent")
        assert not (playlist_video_dir / "nonexistent.json").exists()


class TestPinThumb:
    def test_pin_copies_thumbnail(self, temp_cache):
        cache, _, thumb_dir, _, playlist_thumb_dir = temp_cache
        (thumb_dir / "abc123.jpg").write_bytes(b"fake jpeg data")

        cache.pin_thumb("abc123")

        assert (playlist_thumb_dir / "abc123.jpg").exists()
        assert (playlist_thumb_dir / "abc123.jpg").read_bytes() == b"fake jpeg data"

    def test_pin_no_op_when_no_thumbnail(self, temp_cache):
        cache, _, _, _, playlist_thumb_dir = temp_cache
        cache.pin_thumb("nonexistent")
        assert not (playlist_thumb_dir / "nonexistent.jpg").exists()

    def test_pin_idempotent(self, temp_cache):
        cache, _, thumb_dir, _, playlist_thumb_dir = temp_cache
        (thumb_dir / "abc123.jpg").write_bytes(b"fake jpeg data")

        cache.pin_thumb("abc123")
        cache.pin_thumb("abc123")  # second call is no-op

        assert (playlist_thumb_dir / "abc123.jpg").read_bytes() == b"fake jpeg data"


class TestUnpinVideo:
    def test_unpin_removes_both_files(self, temp_cache):
        cache, _, _, playlist_video_dir, playlist_thumb_dir = temp_cache
        (playlist_video_dir / "abc123.json").write_text('{"id": "abc123"}')
        (playlist_thumb_dir / "abc123.jpg").write_bytes(b"fake")

        cache.unpin_video("abc123")

        assert not (playlist_video_dir / "abc123.json").exists()
        assert not (playlist_thumb_dir / "abc123.jpg").exists()

    def test_unpin_no_error_when_missing(self, temp_cache):
        cache, _, _, _, _ = temp_cache
        cache.unpin_video("nonexistent")  # should not raise


class TestGetVideoRawFallback:
    def test_falls_back_to_playlist_dir(self, temp_cache):
        cache, video_dir, _, playlist_video_dir, _ = temp_cache
        entry = {"id": "abc123", "title": "Pinned Only", "_cached_at": time.time()}
        (playlist_video_dir / "abc123.json").write_text(json.dumps(entry))

        result = cache.get_video_raw("abc123")
        assert result is not None
        assert result["title"] == "Pinned Only"

    def test_prefers_main_cache(self, temp_cache):
        cache, video_dir, _, playlist_video_dir, _ = temp_cache
        main_entry = {"id": "abc123", "title": "Main", "_cached_at": time.time()}
        pinned_entry = {"id": "abc123", "title": "Pinned", "_cached_at": time.time()}
        (video_dir / "abc123.json").write_text(json.dumps(main_entry))
        (playlist_video_dir / "abc123.json").write_text(json.dumps(pinned_entry))

        result = cache.get_video_raw("abc123")
        assert result["title"] == "Main"

    def test_returns_none_when_nowhere(self, temp_cache):
        cache, _, _, _, _ = temp_cache
        assert cache.get_video_raw("missing") is None


class TestThumbPathFallback:
    def test_returns_playlist_path_when_main_missing(self, temp_cache):
        cache, _, thumb_dir, _, playlist_thumb_dir = temp_cache
        (playlist_thumb_dir / "abc123.jpg").write_bytes(b"pinned thumb")

        path = cache.thumb_path("abc123")
        assert path == playlist_thumb_dir / "abc123.jpg"

    def test_returns_main_path_when_exists(self, temp_cache):
        cache, _, thumb_dir, _, playlist_thumb_dir = temp_cache
        (thumb_dir / "abc123.jpg").write_bytes(b"main thumb")
        (playlist_thumb_dir / "abc123.jpg").write_bytes(b"pinned thumb")

        path = cache.thumb_path("abc123")
        assert path == thumb_dir / "abc123.jpg"

    def test_returns_main_path_even_when_missing(self, temp_cache):
        cache, _, thumb_dir, _, _ = temp_cache
        path = cache.thumb_path("missing")
        assert path == thumb_dir / "missing.jpg"


class TestPinAllPlaylistVideos:
    def test_pins_existing_cache_entries(self, temp_cache, monkeypatch):
        cache, video_dir, thumb_dir, playlist_video_dir, playlist_thumb_dir = temp_cache

        entry1 = {"id": "vid1", "title": "Video 1", "_cached_at": time.time()}
        entry2 = {"id": "vid2", "title": "Video 2", "_cached_at": time.time()}
        (video_dir / "vid1.json").write_text(json.dumps(entry1))
        (video_dir / "vid2.json").write_text(json.dumps(entry2))
        (thumb_dir / "vid1.jpg").write_bytes(b"thumb1")

        monkeypatch.setattr("src.playlist.list_names", lambda: ["My List"])
        monkeypatch.setattr("src.playlist.get_playlist", lambda n: ["vid1", "vid2", "vid3"])

        cache.pin_all_playlist_videos()

        assert (playlist_video_dir / "vid1.json").exists()
        assert (playlist_video_dir / "vid2.json").exists()
        assert not (playlist_video_dir / "vid3.json").exists()  # not in cache
        assert (playlist_thumb_dir / "vid1.jpg").exists()

    def test_skips_already_pinned(self, temp_cache, monkeypatch):
        cache, video_dir, _, playlist_video_dir, _ = temp_cache

        entry = {"id": "vid1", "title": "Already Pinned", "_cached_at": time.time()}
        (playlist_video_dir / "vid1.json").write_text(json.dumps(entry))
        (video_dir / "vid1.json").write_text(json.dumps({"id": "vid1", "title": "Main"}))

        monkeypatch.setattr("src.playlist.list_names", lambda: ["List"])
        monkeypatch.setattr("src.playlist.get_playlist", lambda n: ["vid1"])

        cache.pin_all_playlist_videos()

        # Should not overwrite the already-pinned version
        pinned = json.loads((playlist_video_dir / "vid1.json").read_text())
        assert pinned["title"] == "Already Pinned"
