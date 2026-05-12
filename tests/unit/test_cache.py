"""Tests for src/cache.py — disk-based cache with per-key TTL."""

import json
import time
from pathlib import Path

import pytest


class TestGetVideo:
    def test_fresh_returns_data(self, temp_cache):
        from src.cache import VIDEO_DIR

        entry = {"id": "vid1", "title": "Hello", "_cached_at": time.time()}
        (VIDEO_DIR / "vid1.json").write_text(json.dumps(entry))

        result = temp_cache.get_video("vid1")
        assert result is not None
        assert result["title"] == "Hello"

    def test_stale_returns_none(self, temp_cache):
        from src.cache import VIDEO_DIR

        stale_time = time.time() - 86401  # older than metadata TTL
        entry = {"id": "vid1", "title": "Hello", "_cached_at": stale_time}
        (VIDEO_DIR / "vid1.json").write_text(json.dumps(entry))

        assert temp_cache.get_video("vid1") is None

    def test_missing_returns_none(self, temp_cache):
        assert temp_cache.get_video("nonexistent") is None


class TestPutVideo:
    def test_strips_fat_fields(self, temp_cache):
        from src.cache import VIDEO_DIR

        entry = {
            "id": "vid2",
            "title": "Test",
            "formats": [{"format_id": "251"}],
            "requested_formats": [{}],
            "requested_downloads": [{}],
            "automatic_captions": {"en": []},
            "subtitles": {"en": []},
            "heatmap": [1, 2, 3],
            "fragments": [{}],
        }
        temp_cache.put_video(entry)

        stored = json.loads((VIDEO_DIR / "vid2.json").read_text())
        assert "formats" not in stored
        assert "requested_formats" not in stored
        assert "automatic_captions" not in stored
        assert "subtitles" not in stored
        assert "heatmap" not in stored
        assert "fragments" not in stored
        assert stored["title"] == "Test"
        assert "_cached_at" in stored

    def test_no_id_does_nothing(self, temp_cache):
        from src.cache import VIDEO_DIR

        temp_cache.put_video({"title": "No ID"})
        assert list(VIDEO_DIR.glob("*.json")) == []

    def test_uses_webpage_url_basename_as_fallback(self, temp_cache):
        from src.cache import VIDEO_DIR

        temp_cache.put_video({"webpage_url_basename": "fallback_id", "title": "X"})
        assert (VIDEO_DIR / "fallback_id.json").exists()


class TestGetVideoRaw:
    def test_returns_regardless_of_ttl(self, temp_cache):
        from src.cache import VIDEO_DIR

        stale_time = time.time() - 999999
        entry = {"id": "vid3", "title": "Old", "_cached_at": stale_time}
        (VIDEO_DIR / "vid3.json").write_text(json.dumps(entry))

        result = temp_cache.get_video_raw("vid3")
        assert result is not None
        assert result["title"] == "Old"

    def test_falls_back_to_playlist_video_dir(self, temp_cache):
        from src.cache import PLAYLIST_VIDEO_DIR

        entry = {"id": "pvid", "title": "Playlist Entry", "_cached_at": 1.0}
        (PLAYLIST_VIDEO_DIR / "pvid.json").write_text(json.dumps(entry))

        result = temp_cache.get_video_raw("pvid")
        assert result is not None
        assert result["title"] == "Playlist Entry"

    def test_missing_returns_none(self, temp_cache):
        assert temp_cache.get_video_raw("nowhere") is None


class TestFeed:
    def test_put_and_get_fresh(self, temp_cache):
        temp_cache.put_feed("home", ["a", "b", "c"])
        result = temp_cache.get_feed("home")
        assert result == ["a", "b", "c"]

    def test_stale_feed_returns_none(self, temp_cache):
        from src.cache import CACHE_DIR

        stale = {"_cached_at": time.time() - 7200, "ids": ["x"]}
        (CACHE_DIR / "feed_home.json").write_text(json.dumps(stale))

        assert temp_cache.get_feed("home") is None

    def test_get_feed_stale_ignores_ttl(self, temp_cache):
        from src.cache import CACHE_DIR

        stale = {"_cached_at": time.time() - 99999, "ids": ["old1", "old2"]}
        (CACHE_DIR / "feed_home.json").write_text(json.dumps(stale))

        result = temp_cache.get_feed_stale("home")
        assert result == ["old1", "old2"]

    def test_get_feed_stale_missing_returns_none(self, temp_cache):
        assert temp_cache.get_feed_stale("missing") is None


class TestFeedFreshness:
    def test_is_feed_fresh_true(self, temp_cache):
        temp_cache.put_feed("search", ["s1"])
        assert temp_cache.is_feed_fresh("search") is True

    def test_is_feed_fresh_false_when_stale(self, temp_cache):
        from src.cache import CACHE_DIR

        stale = {"_cached_at": time.time() - 99999, "ids": ["x"]}
        (CACHE_DIR / "feed_search.json").write_text(json.dumps(stale))

        assert temp_cache.is_feed_fresh("search") is False

    def test_feed_age_returns_approximate_age(self, temp_cache):
        temp_cache.put_feed("home", ["a"])
        age = temp_cache.feed_age("home")
        assert age is not None
        assert 0 <= age < 2  # should be essentially zero

    def test_feed_age_missing_returns_none(self, temp_cache):
        assert temp_cache.feed_age("nope") is None


class TestThumbPath:
    def test_returns_thumb_dir_path(self, temp_cache):
        from src.cache import THUMB_DIR

        path = temp_cache.thumb_path("vid1")
        assert path == THUMB_DIR / "vid1.jpg"

    def test_falls_back_to_playlist_thumb_dir(self, temp_cache):
        from src.cache import PLAYLIST_THUMB_DIR

        (PLAYLIST_THUMB_DIR / "pvid.jpg").write_bytes(b"\xff\xd8")

        path = temp_cache.thumb_path("pvid")
        assert path == PLAYLIST_THUMB_DIR / "pvid.jpg"

    def test_prefers_main_thumb_dir_when_exists(self, temp_cache):
        from src.cache import THUMB_DIR, PLAYLIST_THUMB_DIR

        (THUMB_DIR / "both.jpg").write_bytes(b"\xff\xd8")
        (PLAYLIST_THUMB_DIR / "both.jpg").write_bytes(b"\xff\xd8")

        path = temp_cache.thumb_path("both")
        assert path == THUMB_DIR / "both.jpg"


class TestPruneVideoCacheFifo:
    def test_evicts_oldest_entries(self, temp_cache):
        from src.cache import VIDEO_DIR

        for i in range(5):
            entry = {"id": f"v{i}", "_cached_at": 1000.0 + i}
            (VIDEO_DIR / f"v{i}.json").write_text(json.dumps(entry))

        temp_cache.prune_video_cache_fifo(max_count=3)

        remaining = list(VIDEO_DIR.glob("*.json"))
        assert len(remaining) == 3
        names = {f.stem for f in remaining}
        assert names == {"v2", "v3", "v4"}

    def test_no_eviction_when_under_limit(self, temp_cache):
        from src.cache import VIDEO_DIR

        for i in range(2):
            entry = {"id": f"v{i}", "_cached_at": 1000.0 + i}
            (VIDEO_DIR / f"v{i}.json").write_text(json.dumps(entry))

        temp_cache.prune_video_cache_fifo(max_count=5)
        assert len(list(VIDEO_DIR.glob("*.json"))) == 2


class TestPruneOldVideos:
    def test_removes_expired_entries(self, temp_cache):
        from src.cache import VIDEO_DIR

        old_time = time.time() - 4 * 86400  # 4 days old
        fresh_time = time.time() - 1 * 86400  # 1 day old

        (VIDEO_DIR / "old.json").write_text(
            json.dumps({"id": "old", "_cached_at": old_time})
        )
        (VIDEO_DIR / "fresh.json").write_text(
            json.dumps({"id": "fresh", "_cached_at": fresh_time})
        )

        temp_cache.prune_old_videos(max_age_days=3, max_count=100)

        assert not (VIDEO_DIR / "old.json").exists()
        assert (VIDEO_DIR / "fresh.json").exists()

    def test_enforces_max_count(self, temp_cache):
        from src.cache import VIDEO_DIR

        now = time.time()
        for i in range(5):
            entry = {"id": f"v{i}", "_cached_at": now - i * 100}
            (VIDEO_DIR / f"v{i}.json").write_text(json.dumps(entry))

        temp_cache.prune_old_videos(max_age_days=30, max_count=2)

        remaining = list(VIDEO_DIR.glob("*.json"))
        assert len(remaining) == 2


class TestPruneOldThumbnails:
    def test_removes_expired_thumbnails(self, temp_cache):
        from src.cache import THUMB_DIR

        old_path = THUMB_DIR / "old.jpg"
        fresh_path = THUMB_DIR / "fresh.jpg"
        old_path.write_bytes(b"\xff\xd8")
        fresh_path.write_bytes(b"\xff\xd8")

        import os
        old_mtime = time.time() - 8 * 86400
        os.utime(old_path, (old_mtime, old_mtime))

        temp_cache.prune_old_thumbnails(max_age_days=7, max_count=300)

        assert not old_path.exists()
        assert fresh_path.exists()

    def test_enforces_max_count(self, temp_cache):
        from src.cache import THUMB_DIR

        for i in range(5):
            p = THUMB_DIR / f"t{i}.jpg"
            p.write_bytes(b"\xff\xd8")
            import os
            mtime = time.time() - i * 100
            os.utime(p, (mtime, mtime))

        temp_cache.prune_old_thumbnails(max_age_days=30, max_count=2)

        remaining = list(THUMB_DIR.glob("*.jpg"))
        assert len(remaining) == 2


class TestHomeStash:
    def test_put_and_get(self, temp_cache):
        entries = [{"id": "s1", "title": "Stash1"}, {"id": "s2", "title": "Stash2"}]
        temp_cache.put_home_stash(entries)

        result = temp_cache.get_home_stash()
        assert len(result) == 2
        assert result[0]["id"] == "s1"

    def test_get_empty_when_no_stash(self, temp_cache):
        assert temp_cache.get_home_stash() == []

    def test_clear_removes_stash(self, temp_cache):
        temp_cache.put_home_stash([{"id": "x"}])
        temp_cache.clear_home_stash()
        assert temp_cache.get_home_stash() == []

    def test_truncates_to_stash_size(self, temp_cache):
        entries = [{"id": f"e{i}"} for i in range(30)]
        temp_cache.put_home_stash(entries)

        result = temp_cache.get_home_stash()
        assert len(result) == 20  # _STASH_SIZE


class TestSuppression:
    def test_register_focus_increments_count(self, temp_cache):
        temp_cache.register_focus("vid1")
        assert not temp_cache.is_suppressed("vid1")

        temp_cache.register_focus("vid1")
        assert not temp_cache.is_suppressed("vid1")

    def test_suppress_after_three_focuses(self, temp_cache):
        temp_cache.register_focus("vid1")
        temp_cache.register_focus("vid1")
        temp_cache.register_focus("vid1")
        assert temp_cache.is_suppressed("vid1")

    def test_already_suppressed_does_not_increment(self, temp_cache):
        for _ in range(3):
            temp_cache.register_focus("vid1")
        assert temp_cache.is_suppressed("vid1")

        # Additional focus calls are no-ops
        temp_cache.register_focus("vid1")
        assert temp_cache.is_suppressed("vid1")

    def test_suppress_video_immediately(self, temp_cache):
        temp_cache.suppress_video("imm")
        assert temp_cache.is_suppressed("imm")
