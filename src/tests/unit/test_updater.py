"""Unit tests for src/updater.py.

Mocks yt_dlp imports and filesystem I/O so tests run fully offline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_updater(tmp_path: Path):
    import src.updater as mod
    return mod


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


# ── update_ytdlp ──────────────────────────────────────────────────────────────

class TestUpdateYtdlp:
    def test_success_returns_true(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("subprocess.run", return_value=MagicMock(returncode=0)),
            patch.object(mod, "get_ytdlp_version", return_value="2026.06.01"),
        ):
            ok = mod.update_ytdlp(verbose=False)
        assert ok is True

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


class TestUpdateExitStatus:
    def test_a_failed_ytdlp_upgrade_fails_the_run(self, tmp_path):
        mod = _make_updater(tmp_path)
        with (
            patch("src.bootstrap.install_all", return_value=True),
            patch.object(mod, "update_ytdlp", return_value=False),
            patch.object(mod, "update_app_code", return_value=True),
        ):
            assert mod.run_all_updates(verbose=False) is False

    def _run_main(self, monkeypatch, tmp_path, result):
        import src.main as main_mod
        import src.updater as updater_mod

        monkeypatch.setattr(sys, "argv", ["termtube", "--update"])
        monkeypatch.setattr(updater_mod, "self_update", lambda: result)
        monkeypatch.setattr(main_mod, "_migrate_legacy_windows_paths", lambda: None)
        monkeypatch.setattr("src.logger.setup", lambda **kw: None)
        with pytest.raises(SystemExit) as exc:
            main_mod.main()
        return exc.value.code

    def test_update_exits_zero_on_success(self, monkeypatch, tmp_path):
        assert self._run_main(monkeypatch, tmp_path, True) == 0

    def test_update_exits_nonzero_on_failure(self, monkeypatch, tmp_path):
        assert self._run_main(monkeypatch, tmp_path, False) == 1
