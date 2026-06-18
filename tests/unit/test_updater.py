"""Unit tests for src/updater.py.

All subprocess calls and filesystem I/O are mocked so these tests run
fully offline with no external tools required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_updater(tmp_path: Path):
    """Return the updater module with its cache paths redirected to *tmp_path*
    so each test gets a clean state."""
    import src.updater as mod

    mod._CACHE_DIR = tmp_path
    mod._LAST_VERSION = tmp_path / "LAST_VERSION"
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
        mock_result = MagicMock(returncode=0, stdout="2026.05.05.233942\n")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            ver = mod.get_ytdlp_version()
        assert ver == "2026.05.05.233942"
        mock_run.assert_called_once_with(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_returns_none_when_not_found(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ver = mod.get_ytdlp_version()
        assert ver is None

    def test_returns_none_on_nonzero_exit(self, tmp_path):
        mod = _make_updater(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=mock_result):
            ver = mod.get_ytdlp_version()
        assert ver is None

    def test_returns_none_on_timeout(self, tmp_path):
        import subprocess
        mod = _make_updater(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 5)):
            ver = mod.get_ytdlp_version()
        assert ver is None


# ── check_for_update_notification ─────────────────────────────────────────────

class TestCheckForUpdateNotification:
    def test_first_run_records_version_no_notification(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch.object(mod, "get_ytdlp_version", return_value="2026.03.17"):
            result = mod.check_for_update_notification()
        assert result is None
        assert mod._LAST_VERSION.read_text() == "2026.03.17"

    def test_same_version_no_notification(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.03.17")
        with patch.object(mod, "get_ytdlp_version", return_value="2026.03.17"):
            result = mod.check_for_update_notification()
        assert result is None

    def test_new_version_returns_notification_string(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.03.17")
        with patch.object(mod, "get_ytdlp_version", return_value="2026.05.05.233942"):
            result = mod.check_for_update_notification()
        assert result is not None
        assert "2026.03.17" in result
        assert "2026.05.05.233942" in result

    def test_new_version_updates_stored_version(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.03.17")
        with patch.object(mod, "get_ytdlp_version", return_value="2026.05.05.233942"):
            mod.check_for_update_notification()
        assert mod._read_last_version() == "2026.05.05.233942"

    def test_undetectable_version_returns_none(self, tmp_path):
        mod = _make_updater(tmp_path)
        mod._write_last_version("2026.03.17")
        with patch.object(mod, "get_ytdlp_version", return_value=None):
            result = mod.check_for_update_notification()
        assert result is None


# ── run_all_updates ────────────────────────────────────────────────────────────

class TestRunAllUpdates:
    def test_success_returns_true(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=True),
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is True

    def test_bootstrap_failure_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is False

    def test_verbose_prints_output(self, tmp_path, capsys):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=True),
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
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


# ── update_ytdlp ──────────────────────────────────────────────────────────────

class TestUpdateYtdlp:
    def test_success_writes_version(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", return_value="2026.06.01"),
        ):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is True
        assert mod._read_last_version() == "2026.06.01"

    def test_not_found_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        with patch("shutil.which", return_value=None):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is False


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
        cookies_tmp = config.cookies_file_path.with_suffix(".tmp")

        def _fake_run(cmd, **kw):
            cookies_tmp.write_text("# Netscape cookies\nfoo\tbar\n")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is True
        assert config.cookies_file_path.exists()
        assert not cookies_tmp.exists()
        assert mod._LAST_COOKIE_REFRESH.exists()

    def test_failure_preserves_existing_cookies(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)
        config.cookies_file_path.write_text("# existing cookies")

        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
        assert config.cookies_file_path.read_text() == "# existing cookies"

    def test_no_cookies_file_configured_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = MagicMock()
        config.cookies_file_path = None

        result = mod.refresh_cookies(config, verbose=False)
        assert result is False

    def test_ytdlp_not_found_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False

    def test_empty_output_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        config = self._make_config(tmp_path)
        cookies_tmp = config.cookies_file_path.with_suffix(".tmp")

        def _fake_run(cmd, **kw):
            cookies_tmp.write_text("")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
