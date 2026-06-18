"""Unit tests for src/updater.py.

All subprocess calls and filesystem I/O are mocked so these tests run
fully offline with no external tools required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_updater(tmp_path: Path):
    """Return the updater module with its cache paths redirected to *tmp_path*
    so each test gets a clean state."""
    import importlib
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


# ── _is_brew_already_uptodate ─────────────────────────────────────────────────

class TestIsBrewAlreadyUptodate:
    def test_brew_upgrade_exit_1_is_uptodate(self, tmp_path):
        mod = _make_updater(tmp_path)
        assert mod._is_brew_already_uptodate(["brew", "upgrade", "mpv"], 1) is True

    def test_brew_upgrade_exit_0_is_not_uptodate(self, tmp_path):
        mod = _make_updater(tmp_path)
        assert mod._is_brew_already_uptodate(["brew", "upgrade", "mpv"], 0) is False

    def test_non_brew_exit_1_is_failure(self, tmp_path):
        mod = _make_updater(tmp_path)
        assert mod._is_brew_already_uptodate(["yt-dlp", "--update-to", "nightly"], 1) is False

    def test_brew_non_upgrade_exit_1_is_failure(self, tmp_path):
        mod = _make_updater(tmp_path)
        assert mod._is_brew_already_uptodate(["brew", "install", "mpv"], 1) is False

    def test_macos_brew_exit_1_treated_as_success(self, tmp_path):
        """Integration: brew upgrade exit 1 should NOT set all_ok=False."""
        mod = _make_updater(tmp_path)

        def _which(cmd):
            return f"/opt/homebrew/bin/{cmd}" if cmd in ("yt-dlp", "brew") else None

        call_count = {"n": 0}
        def _fake_run(cmd, **kw):
            call_count["n"] += 1
            if cmd[0] == "brew":
                return MagicMock(returncode=1)  # "already up to date"
            return MagicMock(returncode=0)  # yt-dlp succeeds

        with (
            patch("subprocess.run", side_effect=_fake_run),
            patch("shutil.which", side_effect=_which),
            patch.multiple("src.updater", IS_MACOS=True, IS_WINDOWS=False, IS_LINUX=False),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is True


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
    def _patch_platform(self, is_macos=False, is_windows=False, is_linux=True):
        return patch.multiple(
            "src.updater",
            IS_MACOS=is_macos,
            IS_WINDOWS=is_windows,
            IS_LINUX=is_linux,
        )

    def test_success_returns_true(self, tmp_path):
        mod = _make_updater(tmp_path)
        mock_result = MagicMock(returncode=0)
        with (
            patch("subprocess.run", return_value=mock_result),
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            self._patch_platform(is_linux=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is True

    def test_failure_returns_false(self, tmp_path):
        mod = _make_updater(tmp_path)
        mock_result = MagicMock(returncode=1)
        with (
            patch("subprocess.run", return_value=mock_result),
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            self._patch_platform(is_linux=True),
        ):
            ok = mod.run_all_updates(verbose=False)
        assert ok is False

    def test_missing_tool_skipped_silently(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("shutil.which", return_value=None),  # no tools on PATH
            self._patch_platform(is_linux=True),
            patch.object(mod, "get_ytdlp_version", return_value=None),
        ):
            ok = mod.run_all_updates(verbose=False)
        # No commands ran → trivially successful
        assert ok is True

    def test_linux_runs_ytdlp_nightly_and_deno_upgrade(self, tmp_path):
        mod = _make_updater(tmp_path)

        def _which(cmd):
            return f"/usr/bin/{cmd}" if cmd in ("yt-dlp", "deno") else None

        run_calls: list = []

        def _fake_run(cmd, **kw):
            run_calls.append(cmd)
            return MagicMock(returncode=0)

        with (
            patch("subprocess.run", side_effect=_fake_run),
            patch("shutil.which", side_effect=_which),
            self._patch_platform(is_linux=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            mod.run_all_updates(verbose=False)

        assert ["yt-dlp", "--update-to", "nightly"] in run_calls
        assert ["deno", "upgrade"] in run_calls
        # mpv / ffmpeg should NOT appear on Linux
        flat = [c for cmd in run_calls for c in cmd]
        assert "mpv" not in flat
        assert "ffmpeg" not in flat

    def test_macos_brew_runs_all_tools(self, tmp_path):
        mod = _make_updater(tmp_path)

        def _which(cmd):
            return f"/opt/homebrew/bin/{cmd}" if cmd in ("yt-dlp", "brew") else None

        run_calls: list = []

        def _fake_run(cmd, **kw):
            run_calls.append(cmd)
            return MagicMock(returncode=0)

        with (
            patch("subprocess.run", side_effect=_fake_run),
            patch("shutil.which", side_effect=_which),
            self._patch_platform(is_macos=True, is_linux=False),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            mod.run_all_updates(verbose=False)

        assert ["yt-dlp", "--update-to", "nightly"] in run_calls
        assert ["brew", "upgrade", "deno"] in run_calls
        assert ["brew", "upgrade", "mpv"] in run_calls
        assert ["brew", "upgrade", "ffmpeg"] in run_calls


    def test_verbose_mode_does_not_suppress_output(self, tmp_path, capsys):
        mod = _make_updater(tmp_path)
        mock_result = MagicMock(returncode=0)
        with (
            patch("subprocess.run", return_value=mock_result),
            patch("shutil.which", return_value="/usr/bin/yt-dlp"),
            self._patch_platform(is_linux=True),
            patch.object(mod, "get_ytdlp_version", return_value="2026.05.05"),
        ):
            mod.run_all_updates(verbose=True)
        out = capsys.readouterr().out
        assert "yt-dlp" in out


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
            # Simulate yt-dlp writing the .tmp file
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
        # Pre-existing cookies.txt
        config.cookies_file_path.write_text("# existing cookies")

        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
        # Existing file should be untouched
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
            # Simulate yt-dlp creating an empty file
            cookies_tmp.write_text("")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
