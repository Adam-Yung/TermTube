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
            result = mod._make_ydl({}, config, auth=True)
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
            result = mod._make_ydl({}, config, auth=True)
        assert result.cookiejar is None


# ── narrowing, invalidation, lazy use ─────────────────────────────────

def _cookie(domain, name="n"):
    from http.cookiejar import Cookie
    return Cookie(0, name, "v", None, False, domain, True, domain.startswith("."), "/", True,
                  False, None, True, None, None, {})


class TestNarrowAndInvalidate:
    def setup_method(self):
        import src.cookies as mod
        mod._jar = None

    teardown_method = setup_method

    def test_only_youtube_and_google_cookies_stay(self):
        import src.cookies as mod
        jar = CookieJar()
        for d in (".youtube.com", "www.youtube.com", ".google.com", "accounts.google.com", ".bank.com", "notyoutube.com"):
            jar.set_cookie(_cookie(d))
        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=jar):
            kept = mod.get_cookiejar(MagicMock())
        assert sorted(c.domain for c in kept) == [".google.com", ".youtube.com", "accounts.google.com", "www.youtube.com"]

    def test_invalidate_forces_a_new_extraction(self):
        import src.cookies as mod
        with patch.object(mod, "resolve_browser", return_value="chrome"), \
             patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=lambda b: CookieJar()) as extract:
            first = mod.get_cookiejar(MagicMock())
            assert mod.get_cookiejar(MagicMock()) is first
            mod.invalidate()
            assert mod.get_cookiejar(MagicMock()) is not first
        assert extract.call_count == 2

    def test_auth_failure_detection(self):
        import src.cookies as mod
        assert mod.is_auth_failure(Exception("Sign in to confirm you're not a bot"))
        assert mod.is_auth_failure(Exception("HTTP Error 403: Forbidden"))
        assert not mod.is_auth_failure(Exception("Video unavailable"))


class _FakeYDL:
    """Stands in for yt_dlp.YoutubeDL; ``script`` items are raised if exceptions, else returned as the info dict."""
    script: list = []

    def __init__(self, opts):
        self.cookiejar = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestLazyAndRetry:
    def test_search_and_channel_fetches_never_read_the_browser(self, tmp_path):
        import src.ytdlp as mod
        _FakeYDL.script = [{"entries": []}] * 6
        cache = MagicMock()
        cache.get_feed.return_value = None
        cache.is_feed_fresh.return_value = False
        with patch.object(mod, "get_cookiejar", side_effect=AssertionError("browser read")), \
             patch("yt_dlp.YoutubeDL", _FakeYDL), patch.object(mod.innertube, "search_videos", return_value=[]), \
             patch.object(mod.time, "sleep"):
            mod.fetch_search_batch("q", None, cache)
            mod.fetch_channel_playlists("https://www.youtube.com/@x", None, cache)
            mod.fetch_channel_videos("https://www.youtube.com/@x", None, cache)

    def test_feed_fetch_reads_the_browser_when_authenticated(self):
        import src.ytdlp as mod
        _FakeYDL.script = [{"entries": []}] * 2
        with patch.object(mod, "get_cookiejar", return_value=None) as get, \
             patch("yt_dlp.YoutubeDL", _FakeYDL), patch.object(mod.time, "sleep"):
            mod.fetch_page_batch("u", None, MagicMock(), auth=True)
        assert get.called

    def test_auth_failure_invalidates_and_retries_once(self):
        import yt_dlp
        import src.ytdlp as mod
        video = {"id": "AAAAAAAAAAA", "title": "t"}
        _FakeYDL.script = [yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot"), {"entries": [video]}]
        with patch.object(mod, "get_cookiejar", return_value=None), patch("yt_dlp.YoutubeDL", _FakeYDL), \
             patch.object(mod, "invalidate") as invalidate, patch.object(mod.time, "sleep"):
            entries = mod.fetch_page_batch("u", None, MagicMock(), auth=True)
        assert [e["id"] for e in entries] == ["AAAAAAAAAAA"]
        invalidate.assert_called_once()

    def test_subscription_list_retries_once_after_auth_failure(self):
        import yt_dlp
        import src.ytdlp as mod
        cache = MagicMock()
        cache.get_feed.return_value = None
        channel = {"id": "UCx", "title": "Chan"}
        _FakeYDL.script = [yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden"), {"entries": [channel]}]
        with patch.object(mod, "get_cookiejar", return_value=None), patch("yt_dlp.YoutubeDL", _FakeYDL), \
             patch.object(mod, "invalidate") as invalidate:
            entries = mod.fetch_subscribed_channels(None, cache)
        assert [e["id"] for e in entries] == ["UCx"]
        invalidate.assert_called_once()
