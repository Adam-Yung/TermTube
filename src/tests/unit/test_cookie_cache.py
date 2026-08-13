"""Unit tests for the session-cached cookie jar system in src/ytdlp.py.

Tests cover:
  - _resolve_browser() logic
  - _get_shared_cookiejar() caching and thread-safety
  - _make_ydl() cookie injection
  - Bug fix verifications (fetch_subscribed_channels, fetch_search_batch)
"""

from __future__ import annotations

import inspect
import threading
from http.cookiejar import CookieJar
from unittest.mock import MagicMock, patch

import pytest


# ── _resolve_browser ──────────────────────────────────────────────────────────

class TestResolveBrowser:
    def test_returns_none_for_none_string(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = "none"
        assert _resolve_browser(config) is None

    def test_returns_none_for_none_value(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = None
        assert _resolve_browser(config) is None

    def test_returns_none_for_empty_string(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = ""
        assert _resolve_browser(config) is None

    def test_returns_detected_browser_for_auto(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = "auto"
        detected = [{"name": "chrome", "label": "Google Chrome"}]
        with patch("src.browsers.detect_installed_browsers", return_value=detected), \
             patch("src.browsers.is_auto_browser", return_value=True):
            result = _resolve_browser(config)
        assert result == "chrome"

    def test_returns_none_when_auto_no_browsers_detected(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = "auto"
        with patch("src.browsers.detect_installed_browsers", return_value=[]), \
             patch("src.browsers.is_auto_browser", return_value=True):
            result = _resolve_browser(config)
        assert result is None

    def test_returns_explicit_browser_as_is(self):
        from src.ytdlp import _resolve_browser
        config = MagicMock()
        config.get.return_value = "firefox"
        with patch("src.browsers.is_auto_browser", return_value=False):
            result = _resolve_browser(config)
        assert result == "firefox"


# ── _get_shared_cookiejar ─────────────────────────────────────────────────────

class TestGetSharedCookiejar:
    def setup_method(self):
        """Reset the global shared jar before each test."""
        import src.ytdlp as mod
        mod._shared_jar = None

    def teardown_method(self):
        """Reset the global shared jar after each test."""
        import src.ytdlp as mod
        mod._shared_jar = None

    def test_returns_jar_on_first_call(self):
        import src.ytdlp as mod
        fake_jar = CookieJar()
        config = MagicMock()
        with patch.object(mod, "_resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=fake_jar):
            result = mod._get_shared_cookiejar(config)
        assert result is fake_jar

    def test_returns_same_jar_on_subsequent_calls(self):
        import src.ytdlp as mod
        fake_jar = CookieJar()
        config = MagicMock()
        with patch.object(mod, "_resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=fake_jar) as mock_extract:
            first = mod._get_shared_cookiejar(config)
            second = mod._get_shared_cookiejar(config)
        assert first is second
        assert mock_extract.call_count == 1

    def test_returns_none_when_browser_is_none(self):
        import src.ytdlp as mod
        config = MagicMock()
        with patch.object(mod, "_resolve_browser", return_value=None):
            result = mod._get_shared_cookiejar(config)
        assert result is None

    def test_returns_none_on_extraction_failure(self):
        import src.ytdlp as mod
        config = MagicMock()
        with patch.object(mod, "_resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=Exception("locked")):
            result = mod._get_shared_cookiejar(config)
        assert result is None

    def test_thread_safety_only_extracts_once(self):
        import src.ytdlp as mod
        fake_jar = CookieJar()
        config = MagicMock()
        call_count = {"n": 0}

        def slow_extract(browser):
            call_count["n"] += 1
            import time
            time.sleep(0.05)
            return fake_jar

        results = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            r = mod._get_shared_cookiejar(config)
            results.append(r)

        with patch.object(mod, "_resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=slow_extract):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert call_count["n"] == 1
        assert all(r is fake_jar for r in results)


# ── _make_ydl ─────────────────────────────────────────────────────────────────


# ── _make_ydl ─────────────────────────────────────────────────────────────────

class TestMakeYdl:
    def setup_method(self):
        import src.ytdlp as mod
        mod._shared_jar = None

    def teardown_method(self):
        import src.ytdlp as mod
        mod._shared_jar = None

    def test_assigns_cookiejar_when_jar_exists(self):
        import src.ytdlp as mod
        fake_jar = MagicMock()  # plain MagicMock is truthy
        config = MagicMock()

        class FakeYDL:
            cookiejar = None
            def __init__(self, opts):
                pass

        with patch.object(mod, "_get_shared_cookiejar", return_value=fake_jar), \
             patch("yt_dlp.YoutubeDL", FakeYDL):
            result = mod._make_ydl({}, config)
        assert result.cookiejar is fake_jar

    def test_does_not_set_cookiejar_when_jar_is_none(self):
        import src.ytdlp as mod
        config = MagicMock()

        class FakeYDL:
            cookiejar = None
            def __init__(self, opts):
                pass

        with patch.object(mod, "_get_shared_cookiejar", return_value=None), \
             patch("yt_dlp.YoutubeDL", FakeYDL):
            result = mod._make_ydl({}, config)
        assert result.cookiejar is None


# ── Bug fix verifications ─────────────────────────────────────────────────────

class TestBugFixVerifications:
    """Verify that previous bug fixes remain in place."""

    def test_fetch_subscribed_channels_no_count_parameter(self):
        """fetch_subscribed_channels should not require a 'count' parameter —
        the playlist limit is hardcoded internally to 200."""
        from src.ytdlp import fetch_subscribed_channels
        sig = inspect.signature(fetch_subscribed_channels)
        params = list(sig.parameters.keys())
        assert "count" not in params

    def test_fetch_subscribed_channels_uses_hardcoded_200(self):
        """Verify the hardcoded playlistend=200 is in the source."""
        import src.ytdlp as mod
        source = inspect.getsource(mod.fetch_subscribed_channels)
        assert "opts['playlistend'] = 200" in source

    def test_fetch_search_batch_no_on_first_batch_reference(self):
        """fetch_search_batch must not reference on_first_batch in its body
        (the copy-pasted block was removed)."""
        import src.ytdlp as mod
        source = inspect.getsource(mod.fetch_search_batch)
        assert "on_first_batch" not in source
