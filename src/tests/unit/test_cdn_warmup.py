"""Tests for CDN readiness probing in src/ytdlp.py."""

import threading
import time
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def clear_caches():
    """Reset module-level caches between tests."""
    import src.ytdlp as ytdlp
    ytdlp._stream_cache.clear()
    ytdlp._cdn_ready_events.clear()
    yield
    ytdlp._stream_cache.clear()
    ytdlp._cdn_ready_events.clear()


class TestPutCachedStreamUrl:
    def test_stores_url_with_timestamp(self):
        import src.ytdlp as ytdlp

        with patch.object(ytdlp, '_start_cdn_probe'):
            ytdlp.put_cached_stream_url("vid1", "ba/b", ["https://example.com/stream"])

        result = ytdlp.get_cached_stream_url("vid1", "ba/b")
        assert result == ["https://example.com/stream"]

    def test_triggers_cdn_probe(self):
        import src.ytdlp as ytdlp

        with patch.object(ytdlp, '_start_cdn_probe') as mock_probe:
            ytdlp.put_cached_stream_url("vid1", "ba/b", ["https://cdn.example.com/a"])

        mock_probe.assert_called_once_with("vid1", "ba/b", ["https://cdn.example.com/a"])

    def test_evicts_oldest_when_over_capacity(self):
        import src.ytdlp as ytdlp

        with patch.object(ytdlp, '_start_cdn_probe'):
            for i in range(21):
                ytdlp.put_cached_stream_url(f"vid{i}", "ba/b", [f"https://cdn/{i}"])

        assert len(ytdlp._stream_cache) == 20


class TestStartCdnProbe:
    def test_creates_event_and_starts_thread(self):
        import src.ytdlp as ytdlp

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value = MagicMock()
            ytdlp._start_cdn_probe("vid1", "ba/b", ["https://cdn.example.com/a"])

        key = "vid1:ba/b"
        assert key in ytdlp._cdn_ready_events
        assert isinstance(ytdlp._cdn_ready_events[key], threading.Event)
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_evicts_oldest_event_when_over_capacity(self):
        import src.ytdlp as ytdlp

        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value = MagicMock()
            for i in range(26):
                ytdlp._start_cdn_probe(f"vid{i}", "ba/b", [f"https://cdn/{i}"])

        assert len(ytdlp._cdn_ready_events) <= 25


class TestWaitForStreamUrlReady:
    def test_returns_instantly_when_event_already_set(self):
        import src.ytdlp as ytdlp

        key = "vid1:ba/b"
        ev = threading.Event()
        ev.set()
        ytdlp._cdn_ready_events[key] = ev

        t0 = time.time()
        ytdlp.wait_for_stream_url_ready("vid1", "ba/b")
        elapsed = time.time() - t0

        assert elapsed < 0.1

    def test_blocks_until_event_is_set(self):
        import src.ytdlp as ytdlp

        key = "vid1:ba/b"
        ev = threading.Event()
        ytdlp._cdn_ready_events[key] = ev

        def set_after_delay():
            time.sleep(0.3)
            ev.set()

        threading.Thread(target=set_after_delay, daemon=True).start()

        t0 = time.time()
        ytdlp.wait_for_stream_url_ready("vid1", "ba/b")
        elapsed = time.time() - t0

        assert 0.2 < elapsed < 1.0

    def test_falls_back_to_cache_age_when_no_event(self):
        import src.ytdlp as ytdlp

        # Simulate URL cached 10 seconds ago (well past warmup)
        ytdlp._stream_cache["vid1:ba/b"] = (time.time() - 10, ["https://cdn/x"])

        t0 = time.time()
        ytdlp.wait_for_stream_url_ready("vid1", "ba/b")
        elapsed = time.time() - t0

        assert elapsed < 0.1  # no-op since URL is old enough

    def test_returns_immediately_when_no_cache_entry(self):
        import src.ytdlp as ytdlp

        t0 = time.time()
        ytdlp.wait_for_stream_url_ready("nonexistent", "ba/b")
        elapsed = time.time() - t0

        assert elapsed < 0.1


class TestProbeCdnReady:
    def test_sets_event_on_success(self):
        import src.ytdlp as ytdlp

        key = "vid1:ba/b"
        ev = threading.Event()
        ytdlp._cdn_ready_events[key] = ev

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'\x00'

        with patch('urllib.request.urlopen', return_value=mock_resp):
            ytdlp._probe_cdn_ready("https://cdn.example.com/stream", key)

        assert ev.is_set()

    def test_retries_on_failure_then_sets_event(self):
        import src.ytdlp as ytdlp
        import urllib.error

        key = "vid1:ba/b"
        ev = threading.Event()
        ytdlp._cdn_ready_events[key] = ev

        call_count = [0]
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'\x00'

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise urllib.error.URLError("Connection refused")
            return mock_resp

        with patch('urllib.request.urlopen', side_effect=side_effect):
            with patch('time.sleep'):  # skip actual sleeps in test
                ytdlp._probe_cdn_ready("https://cdn.example.com/stream", key)

        assert ev.is_set()
        assert call_count[0] == 3
