"""Unit tests for the session-cached cookie jar system in src/ytdlp.py.

Tests cover:
  - resolve_browser() logic
  - get_cookiejar() caching and thread-safety
  - _make_ydl() cookie injection
  - Bug fix verifications (fetch_subscribed_channels, fetch_search_batch)
"""

from __future__ import annotations

import inspect
import threading
from http.cookiejar import CookieJar
from unittest.mock import MagicMock, patch

import pytest


# ── resolve_browser ──────────────────────────────────────────────────────────

class TestResolveBrowser:
    def test_returns_none_for_none_string(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = "none"
        assert resolve_browser(config) is None

    def test_returns_none_for_none_value(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = None
        assert resolve_browser(config) is None

    def test_returns_none_for_empty_string(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = ""
        assert resolve_browser(config) is None

    def test_returns_detected_browser_for_auto(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = "auto"
        detected = [{"name": "chrome", "label": "Google Chrome"}]
        with patch("src.browsers.detect_installed_browsers", return_value=detected), \
             patch("src.browsers.is_auto_browser", return_value=True):
            result = resolve_browser(config)
        assert result == "chrome"

    def test_returns_none_when_auto_no_browsers_detected(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = "auto"
        with patch("src.browsers.detect_installed_browsers", return_value=[]), \
             patch("src.browsers.is_auto_browser", return_value=True):
            result = resolve_browser(config)
        assert result is None

    def test_returns_explicit_browser_as_is(self):
        from src.cookies import resolve_browser
        config = MagicMock()
        config.get.return_value = "firefox"
        with patch("src.browsers.is_auto_browser", return_value=False):
            result = resolve_browser(config)
        assert result == "firefox"


# ── get_cookiejar ─────────────────────────────────────────────────────

class TestGetSharedCookiejar:
    def setup_method(self):
        """Reset the global shared jar before each test."""
        import src.cookies as mod
        mod._jar = None

    def teardown_method(self):
        """Reset the global shared jar after each test."""
        import src.cookies as mod
        mod._jar = None

    def test_returns_jar_on_first_call(self):
        import src.cookies as mod
        fake_jar = CookieJar()
        config = MagicMock()
        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=fake_jar):
            result = mod.get_cookiejar(config)
        assert result is fake_jar

    def test_returns_same_jar_on_subsequent_calls(self):
        import src.cookies as mod
        fake_jar = CookieJar()
        config = MagicMock()
        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=fake_jar) as mock_extract:
            first = mod.get_cookiejar(config)
            second = mod.get_cookiejar(config)
        assert first is second
        assert mock_extract.call_count == 1

    def test_returns_none_when_browser_is_none(self):
        import src.cookies as mod
        config = MagicMock()
        with patch.object(mod, "resolve_browser", return_value=None):
            result = mod.get_cookiejar(config)
        assert result is None

    def test_returns_none_on_extraction_failure(self):
        import src.cookies as mod
        config = MagicMock()
        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=Exception("locked")):
            result = mod.get_cookiejar(config)
        assert result is None

    def test_thread_safety_only_extracts_once(self):
        import src.cookies as mod
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
            r = mod.get_cookiejar(config)
            results.append(r)

        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=slow_extract):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert call_count["n"] == 1
        assert all(r is fake_jar for r in results)


# ── _make_ydl ─────────────────────────────────────────────────────────────────

class TestMakeYdl:
    def setup_method(self):
        import src.cookies as cookies
        cookies._jar = None

    def teardown_method(self):
        import src.cookies as cookies
        cookies._jar = None

    def test_assigns_cookiejar_when_jar_exists(self):
        import src.ytdlp as mod
        fake_jar = MagicMock()  # plain MagicMock is truthy
        config = MagicMock()

        class FakeYDL:
            cookiejar = None
            def __init__(self, opts):
                pass

        with patch.object(mod, "get_cookiejar", return_value=fake_jar), \
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

        with patch.object(mod, "get_cookiejar", return_value=None), \
             patch("yt_dlp.YoutubeDL", FakeYDL):
            result = mod._make_ydl({}, config)
        assert result.cookiejar is None
