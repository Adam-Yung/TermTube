"""Unit tests for src/updater.py.

Mocks yt_dlp imports and filesystem I/O so tests run fully offline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_updater(tmp_path: Path):
    """Return the updater module with its cache paths redirected to *tmp_path*
    so each test gets a clean state."""
    import src.updater as mod

    mod._CACHE_DIR = tmp_path
    mod._LAST_VERSION = tmp_path / "LAST_VERSION"
    mod._PENDING_VERSION_NOTIFY = tmp_path / "PENDING_VERSION_NOTIFY"
    mod._LAST_COOKIE_REFRESH = tmp_path / "LAST_COOKIE_REFRESH"
    return mod


# ── Version file helpers ───────────────────────────────────────────────────────

class TestVersionHelpers:
    def test_write_last_version_persists(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.05.05.233942")
        assert mod._LAST_VERSION.read_text() == "2026.05.05.233942"

    def test_read_last_version_missing_returns_none(self, tmp_path):
        mod = _make_updater(tmp_path)
        assert mod._read_last_version() is None

    def test_read_last_version_roundtrip(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.03.17")
        assert mod._read_last_version() == "2026.03.17"


# ── get_ytdlp_version ─────────────────────────────────────────────────────────

class TestGetYtdlpVersion:
    def test_returns_version_string(self, tmp_path):
        mod = _make_updater(tmp_path)
        mock_version = MagicMock()
        mock_version.__version__ = "2026.05.05.233942"
        mock_yt_dlp = MagicMock()
        mock_yt_dlp.version = mock_version

        with patch.dict("sys.modules", {"yt_dlp": mock_yt_dlp, "yt_dlp.version": mock_version}):
            ver = mod.get_ytdlp_version()
        assert ver == "2026.05.05.233942"

    def test_returns_none_when_import_fails(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch.dict("sys.modules", {"yt_dlp": None}):
            with patch("builtins.__import__", side_effect=ImportError("no yt_dlp")):
                ver = mod.get_ytdlp_version()
        assert ver is None

    def test_returns_none_on_attribute_error(self, tmp_path):
        mod = _make_updater(tmp_path)
        mock_yt_dlp = MagicMock(spec=[])
        del mock_yt_dlp.version

        with patch.dict("sys.modules", {"yt_dlp": mock_yt_dlp}):
            with patch("builtins.__import__", side_effect=AttributeError("no version")):
                ver = mod.get_ytdlp_version()
        assert ver is None


# ── check_for_update_notification ─────────────────────────────────────────────

class TestCheckForUpdateNotification:
    def test_no_pending_file_returns_none(self, tmp_path):
        mod = _make_updater(tmp_path)
        result = mod.check_for_update_notification()
        assert result is None

    def test_pending_file_returns_message_and_deletes(self, tmp_path):
        mod = _make_updater(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        mod._PENDING_VERSION_NOTIFY.write_text("yt-dlp updated  2026.03.17 -> 2026.05.05")
        result = mod.check_for_update_notification()
        assert result is not None
        assert "2026.03.17" in result
        assert "2026.05.05" in result
        assert not mod._PENDING_VERSION_NOTIFY.exists()

    def test_empty_pending_file_returns_none(self, tmp_path):
        mod = _make_updater(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        mod._PENDING_VERSION_NOTIFY.write_text("")
        result = mod.check_for_update_notification()
        assert result is None

    def test_only_fires_once(self, tmp_path):
        mod = _make_updater(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        mod._PENDING_VERSION_NOTIFY.write_text("yt-dlp updated  old -> new")
        first = mod.check_for_update_notification()
        second = mod.check_for_update_notification()
        assert first is not None
        assert second is None


# ── update_ytdlp ──────────────────────────────────────────────────────────────

class TestUpdateYtdlp:
    def test_success_writes_version(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", return_value="2026.06.01"),
        ):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is True
        assert mod._read_last_version() == "2026.06.01"

    def test_pip_failure_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is False

    def test_pip_not_found_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is False

    def test_timeout_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip", 120)):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is False

    def test_version_change_writes_notification(self, tmp_path):
        mod = _make_updater(tmp_path)
        call_count = [0]
        def _fake_version():
            call_count[0] += 1
            if call_count[0] <= 1:
                return "2026.01.01"
            return "2026.06.01"

        with (
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", side_effect=_fake_version),
        ):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is True
        assert mod._PENDING_VERSION_NOTIFY.exists()
        assert "2026.01.01" in mod._PENDING_VERSION_NOTIFY.read_text()
        assert "2026.06.01" in mod._PENDING_VERSION_NOTIFY.read_text()


# ── run_all_updates ────────────────────────────────────────────────────────────

class TestRunAllUpdates:
    def test_success_returns_true(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=True),
            patch.object(mod, "update_ytdlp", return_value=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
            patch.object(mod, "update_app_code", return_value=True),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is True

    def test_bootstrap_failure_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=False),
            patch.object(mod, "update_ytdlp", return_value=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
            patch.object(mod, "update_app_code", return_value=False),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is False

    def test_verbose_prints_output(self, tmp_path, capsys):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=True),
            patch.object(mod, "update_ytdlp", return_value=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
            patch.object(mod, "update_app_code", return_value=True),
        ):
            mod.run_all_updates(verbose=True)
        out = capsys.readouterr().out
        assert "Re-downloading" in out or "yt-dlp" in out


# ── update_tool ───────────────────────────────────────────────────────────────

class TestUpdateTool:
    def test_delegates_to_bootstrap_install_tool(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("src.bootstrap.install_tool", return_value=True) as mock_install:
            result = mod.update_tool("yt-dlp", verbose=False)
        assert result is True
        mock_install.assert_called_once_with("yt-dlp", force=True)

    def test_returns_false_on_failure(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("src.bootstrap.install_tool", return_value=False):
            result = mod.update_tool("ffmpeg", verbose=False)
        assert result is False


# ── refresh_cookies ───────────────────────────────────────────────────────────

class TestRefreshCookies:
    def _make_config(self, tmp_path: Path):
        """Create a minimal Config-like object for testing."""
        mock = MagicMock()
        mock.cookies_file_path = tmp_path / "cookies.txt"
        mock.get.return_value = "chrome"
        return mock

    def test_success_writes_cookies_and_touches_sentinel(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)
        tmp_cookie = config.cookies_file_path.with_suffix(".tmp")

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_extract(url, download=False):
            tmp_cookie.parent.mkdir(parents=True, exist_ok=True)
            tmp_cookie.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
            )
            return {}

        mock_ydl.extract_info = fake_extract

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.browsers.is_auto_browser", return_value=False):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is True
        assert config.cookies_file_path.exists()
        assert not tmp_cookie.exists()
        assert mod._LAST_COOKIE_REFRESH.exists()

    def test_failure_preserves_existing_cookies(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)
        config.cookies_file_path.write_text("# existing cookies")

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = Exception("browser locked")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.browsers.is_auto_browser", return_value=False):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
        assert config.cookies_file_path.read_text() == "# existing cookies"

    def test_no_cookies_file_configured_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = MagicMock()
        config.cookies_file_path = None

        result = mod.refresh_cookies(config, verbose=False)
        assert result is False

    def test_empty_output_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)
        tmp_cookie = config.cookies_file_path.with_suffix(".tmp")

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_extract(url, download=False):
            tmp_cookie.parent.mkdir(parents=True, exist_ok=True)
            tmp_cookie.write_text("")
            return {}

        mock_ydl.extract_info = fake_extract

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.browsers.is_auto_browser", return_value=False):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
