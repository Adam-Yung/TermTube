"""Tests for src/sponsorblock.py -- SponsorBlock API client with disk caching."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.sponsorblock import (
    _CACHE_TTL,
    Segment,
    _cached_ssl_context,
    _get_ssl_context,
    _read_cache,
    _read_ssl_pref,
    _write_cache,
    fetch_segments,
)


def _assert_segment(seg, *, start: float, end: float, category: str):
    """Assert segment fields without relying on dataclass __eq__ (which breaks
    when other tests reload the module and create a new Segment class object)."""
    assert seg.start == start
    assert seg.end == end
    assert seg.category == category


def _bucket(video_id: str, segments: list[dict]) -> list[dict]:
    """A hash-prefix response (recorded shape): the played video plus another video from the same bucket."""
    other = {"videoID": "otherVideo1", "hash": "ab" * 32, "segments": [{"segment": [1.0, 2.0], "category": "sponsor"}]}
    return [other, {"videoID": video_id, "hash": "cd" * 32, "segments": segments}]


def _response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── Segment dataclass ─────────────────────────────────────────────────────────


class TestSegment:
    def test_creation(self):
        seg = Segment(start=10.5, end=20.3, category="sponsor")
        assert seg.start == 10.5
        assert seg.end == 20.3
        assert seg.category == "sponsor"

    def test_frozen(self):
        seg = Segment(start=0.0, end=5.0, category="selfpromo")
        with pytest.raises(AttributeError):
            seg.start = 1.0

    def test_equality(self):
        a = Segment(start=1.0, end=2.0, category="sponsor")
        b = Segment(start=1.0, end=2.0, category="sponsor")
        assert a == b


# ── _read_cache ───────────────────────────────────────────────────────────────


class TestReadCache:
    def test_returns_none_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path / "sb")
        result = _read_cache("nonexistent_video")
        assert result is None

    def test_returns_none_when_ttl_expired(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        data = [{"start": 0.0, "end": 5.0, "category": "sponsor"}]
        cache_file = cache_dir / "old_video.json"
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        expired_time = time.time() - _CACHE_TTL - 100
        import os
        os.utime(cache_file, (expired_time, expired_time))

        result = _read_cache("old_video")
        assert result is None

    def test_returns_segments_when_fresh(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        data = [
            {"start": 10.0, "end": 20.0, "category": "sponsor"},
            {"start": 50.0, "end": 60.0, "category": "selfpromo"},
        ]
        cache_file = cache_dir / "fresh_video.json"
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        result = _read_cache("fresh_video")
        assert result is not None
        assert len(result) == 2
        _assert_segment(result[0], start=10.0, end=20.0, category="sponsor")
        _assert_segment(result[1], start=50.0, end=60.0, category="selfpromo")

    def test_returns_empty_list_for_cached_empty(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        cache_file = cache_dir / "empty_video.json"
        cache_file.write_text(json.dumps([]), encoding="utf-8")

        result = _read_cache("empty_video")
        assert result == []

    def test_returns_none_on_corrupt_json(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        cache_file = cache_dir / "corrupt_video.json"
        cache_file.write_text("not valid json{{{", encoding="utf-8")

        result = _read_cache("corrupt_video")
        assert result is None


# ── _write_cache ──────────────────────────────────────────────────────────────


class TestWriteCache:
    def test_creates_directory_and_writes_json(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "new_dir" / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        segments = [
            Segment(start=5.0, end=15.0, category="sponsor"),
            Segment(start=30.0, end=45.0, category="selfpromo"),
        ]
        _write_cache("test_vid", segments)

        assert cache_dir.exists()
        cache_file = cache_dir / "test_vid.json"
        assert cache_file.exists()

        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0] == {"start": 5.0, "end": 15.0, "category": "sponsor"}
        assert data[1] == {"start": 30.0, "end": 45.0, "category": "selfpromo"}

    def test_writes_empty_list(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        _write_cache("no_segments", [])

        cache_file = cache_dir / "no_segments.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert data == []


# ── fetch_segments ────────────────────────────────────────────────────────────


class TestFetchSegments:
    def test_returns_cached_data_when_fresh(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)

        data = [{"start": 1.0, "end": 2.0, "category": "sponsor"}]
        (cache_dir / "cached_vid.json").write_text(json.dumps(data), encoding="utf-8")

        result = fetch_segments("cached_vid")
        assert len(result) == 1
        _assert_segment(result[0], start=1.0, end=2.0, category="sponsor")

    def test_returns_empty_for_empty_video_id(self):
        assert fetch_segments("") == []

    def test_handles_http_404_no_segments(self, tmp_path, monkeypatch):
        import urllib.error

        cache_dir = tmp_path / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        error = urllib.error.HTTPError(
            url="http://example.com", code=404,
            msg="Not Found", hdrs={}, fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            result = fetch_segments("no_segments_vid")

        assert result == []
        cache_file = cache_dir / "no_segments_vid.json"
        assert cache_file.exists()
        assert json.loads(cache_file.read_text(encoding="utf-8")) == []

    def test_handles_network_error_gracefully(self, tmp_path, monkeypatch):
        import urllib.error

        cache_dir = tmp_path / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=error):
            result = fetch_segments("network_error_vid")

        assert result == []

    def test_parses_api_response_correctly(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        api_response = _bucket("parse_test_vid", [
            {"segment": [0.0, 30.5], "category": "sponsor", "UUID": "aaa"},
            {"segment": [120.0, 150.0], "category": "selfpromo", "UUID": "bbb"},
            {"segment": [200.0, 210.0], "category": "sponsor", "UUID": "ccc"},
        ])
        response_bytes = json.dumps(api_response).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_segments("parse_test_vid")

        assert len(result) == 3
        _assert_segment(result[0], start=0.0, end=30.5, category="sponsor")
        _assert_segment(result[1], start=120.0, end=150.0, category="selfpromo")
        _assert_segment(result[2], start=200.0, end=210.0, category="sponsor")

    def test_skips_malformed_segments(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "sb"
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", cache_dir)
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        api_response = _bucket("malformed_vid", [
            {"segment": [0.0, 10.0], "category": "sponsor"},
            {"segment": "invalid", "category": "sponsor"},
            {"segment": [20.0], "category": "sponsor"},
            {"category": "sponsor"},
        ])
        response_bytes = json.dumps(api_response).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_segments("malformed_vid")

        assert len(result) == 1
        _assert_segment(result[0], start=0.0, end=10.0, category="sponsor")


class TestHashPrefix:
    def test_request_sends_the_prefix_not_the_video_id(self, tmp_path, monkeypatch):
        import hashlib

        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path / "sb")
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())
        payload = _bucket("secretVid11", [{"segment": [5.0, 9.0], "category": "sponsor"}])

        with patch("urllib.request.urlopen", return_value=_response(payload)) as opened:
            fetch_segments("secretVid11")

        url = opened.call_args.args[0].full_url
        prefix = hashlib.sha256(b"secretVid11").hexdigest()[:4]
        assert url.startswith(f"https://sponsor.ajay.app/api/skipSegments/{prefix}?")
        assert "secretVid11" not in url

    def test_other_videos_in_the_bucket_are_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path / "sb")
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())
        payload = _bucket("wantedVid11", [{"segment": [5.0, 9.0], "category": "sponsor"}])

        with patch("urllib.request.urlopen", return_value=_response(payload)):
            result = fetch_segments("wantedVid11")

        assert len(result) == 1
        _assert_segment(result[0], start=5.0, end=9.0, category="sponsor")

    def test_bucket_without_the_video_gives_no_segments(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path / "sb")
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        with patch("urllib.request.urlopen", return_value=_response(_bucket("else1234567", []))):
            assert fetch_segments("absentVid11") == []

    def test_non_list_response_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path / "sb")
        monkeypatch.setattr("src.sponsorblock._ssl_context", MagicMock())

        with patch("urllib.request.urlopen", return_value=_response({"error": "x"})):
            assert fetch_segments("anyVid12345") == []


# ── _get_ssl_context / _cached_ssl_context ────────────────────────────────────


class TestSSLContext:
    def test_get_ssl_context_returns_context(self):
        with patch("src.sponsorblock._read_ssl_pref", return_value=None), \
             patch("src.sponsorblock._write_ssl_pref"):
            ctx = _get_ssl_context()

        import ssl
        assert isinstance(ctx, ssl.SSLContext)

    def test_no_context_builds_means_none_and_no_unverified_pref(self):
        with patch("src.sponsorblock._read_ssl_pref", return_value=None), \
             patch("src.sponsorblock._build_ssl_context", side_effect=Exception("probe failed")), \
             patch("src.sponsorblock._write_ssl_pref") as write:
            assert _get_ssl_context() is None
        write.assert_not_called()

    def test_an_old_unverified_pref_on_disk_is_ignored(self, tmp_path, monkeypatch):
        pref = tmp_path / "ssl_pref"
        pref.write_text("unverified", encoding="utf-8")
        monkeypatch.setattr("src.sponsorblock._SSL_PREF_PATH", pref)
        assert _read_ssl_pref() is None

    def test_fetch_fails_closed_without_a_context(self, monkeypatch):
        monkeypatch.setattr("src.sponsorblock._ssl_context", None)
        monkeypatch.setattr("src.sponsorblock._get_ssl_context", lambda: None)
        with patch("src.sponsorblock._do_fetch") as fetch, patch("src.sponsorblock._read_cache", return_value=None), \
             patch("src.sponsorblock._write_cache"):
            assert fetch_segments("AAAAAAAAAAA", ["sponsor"]) == []
        fetch.assert_not_called()

    def test_cached_ssl_context_caches_result(self, monkeypatch):
        import ssl
        monkeypatch.setattr("src.sponsorblock._ssl_context", None)

        mock_ctx = ssl.create_default_context()
        with patch("src.sponsorblock._get_ssl_context", return_value=mock_ctx) as mock_get:
            first = _cached_ssl_context()
            second = _cached_ssl_context()

        assert first is mock_ctx
        assert second is mock_ctx
        mock_get.assert_called_once()
