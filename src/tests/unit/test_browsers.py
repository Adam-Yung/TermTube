"""Unit tests for src/browsers.py — browser auto-detection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestDetectMacOS:
    """Test macOS browser detection via .app bundle checks."""

    @patch("src.browsers.IS_MACOS", True)
    @patch("src.browsers.IS_WINDOWS", False)
    @patch("src.browsers.IS_LINUX", False)
    def test_detects_chrome_in_applications(self, tmp_path):
        apps = tmp_path / "Applications"
        (apps / "Google Chrome.app").mkdir(parents=True)

        from src import browsers

        def patched_detect():
            found = []
            search_dirs = [apps]
            for name, bundle in browsers._MACOS_APP_BUNDLES.items():
                for base in search_dirs:
                    if (base / bundle).exists():
                        found.append({"name": name, "label": browsers._BROWSER_LABELS[name]})
                        break
            return found

        with patch.object(browsers, "_detect_macos", patched_detect):
            result = browsers.detect_installed_browsers()

        assert len(result) == 1
        assert result[0]["name"] == "chrome"
        assert result[0]["label"] == "Google Chrome"

    @patch("src.browsers.IS_MACOS", True)
    @patch("src.browsers.IS_WINDOWS", False)
    @patch("src.browsers.IS_LINUX", False)
    def test_detects_multiple_browsers(self, tmp_path):
        apps = tmp_path / "Applications"
        (apps / "Google Chrome.app").mkdir(parents=True)
        (apps / "Firefox.app").mkdir(parents=True)
        (apps / "Safari.app").mkdir(parents=True)

        from src import browsers

        def patched_detect():
            found = []
            search_dirs = [apps]
            for name, bundle in browsers._MACOS_APP_BUNDLES.items():
                for base in search_dirs:
                    if (base / bundle).exists():
                        found.append({"name": name, "label": browsers._BROWSER_LABELS[name]})
                        break
            return found

        with patch.object(browsers, "_detect_macos", patched_detect):
            result = browsers.detect_installed_browsers()

        names = [b["name"] for b in result]
        assert "chrome" in names
        assert "firefox" in names
        assert "safari" in names
        assert len(result) == 3

    @patch("src.browsers.IS_MACOS", True)
    @patch("src.browsers.IS_WINDOWS", False)
    @patch("src.browsers.IS_LINUX", False)
    def test_no_browsers_returns_empty(self, tmp_path):
        from src import browsers

        with patch.object(browsers, "_detect_macos", return_value=[]):
            result = browsers.detect_installed_browsers()

        assert result == []


class TestDetectWindows:
    """Test Windows browser detection via exe path checks."""

    def test_detects_chrome_in_program_files(self, tmp_path):
        (tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe").parent.mkdir(parents=True)
        (tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe").touch()

        from src import browsers

        env = {"ProgramFiles": str(tmp_path), "ProgramFiles(x86)": "", "LOCALAPPDATA": ""}
        with patch.dict("os.environ", env, clear=False):
            result = browsers._detect_windows()

        assert len(result) == 1
        assert result[0]["name"] == "chrome"

    def test_detects_edge_and_firefox(self, tmp_path):
        (tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe").parent.mkdir(parents=True)
        (tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe").touch()
        (tmp_path / "Mozilla Firefox" / "firefox.exe").parent.mkdir(parents=True)
        (tmp_path / "Mozilla Firefox" / "firefox.exe").touch()

        from src import browsers

        env = {"ProgramFiles": str(tmp_path), "ProgramFiles(x86)": "", "LOCALAPPDATA": ""}
        with patch.dict("os.environ", env, clear=False):
            result = browsers._detect_windows()

        names = [b["name"] for b in result]
        assert "edge" in names
        assert "firefox" in names
        assert len(result) == 2

    def test_checks_localappdata(self, tmp_path):
        (tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe").parent.mkdir(parents=True)
        (tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe").touch()

        from src import browsers

        env = {"ProgramFiles": "", "ProgramFiles(x86)": "", "LOCALAPPDATA": str(tmp_path)}
        with patch.dict("os.environ", env, clear=False):
            result = browsers._detect_windows()

        assert len(result) == 1
        assert result[0]["name"] == "chrome"

    def test_no_browsers_returns_empty(self, tmp_path):
        from src import browsers

        env = {"ProgramFiles": str(tmp_path), "ProgramFiles(x86)": "", "LOCALAPPDATA": ""}
        with patch.dict("os.environ", env, clear=False):
            result = browsers._detect_windows()

        assert result == []


class TestDetectLinux:
    """Test Linux browser detection via shutil.which."""

    def test_detects_firefox_on_path(self):
        from src import browsers

        def fake_which(exe):
            return "/usr/bin/firefox" if exe == "firefox" else None

        with patch("shutil.which", side_effect=fake_which):
            result = browsers._detect_linux()

        assert len(result) == 1
        assert result[0]["name"] == "firefox"

    def test_detects_multiple_on_path(self):
        from src import browsers

        available = {"google-chrome", "brave-browser"}

        def fake_which(exe):
            return f"/usr/bin/{exe}" if exe in available else None

        with patch("shutil.which", side_effect=fake_which):
            result = browsers._detect_linux()

        names = [b["name"] for b in result]
        assert "chrome" in names
        assert "brave" in names

    def test_no_browsers_returns_empty(self):
        from src import browsers

        with patch("shutil.which", return_value=None):
            result = browsers._detect_linux()

        assert result == []


class TestHelperFunctions:
    """Test utility functions."""

    def test_get_browser_label_known(self):
        from src.browsers import get_browser_label
        assert get_browser_label("chrome") == "Google Chrome"
        assert get_browser_label("firefox") == "Firefox"
        assert get_browser_label("edge") == "Microsoft Edge"

    def test_get_browser_label_unknown(self):
        from src.browsers import get_browser_label
        assert get_browser_label("unknown") == "Unknown"

    def test_is_auto_browser(self):
        from src.browsers import is_auto_browser
        assert is_auto_browser(None) is True
        assert is_auto_browser("auto") is True
        assert is_auto_browser("") is True
        assert is_auto_browser("chrome") is False
        assert is_auto_browser("firefox") is False


class TestRefreshCookiesIntegration:
    """Test that refresh_cookies correctly uses auto-detection."""

    def test_explicit_browser_param_overrides_detection(self, tmp_path):
        """When browser= is passed to refresh_cookies, it should be used directly."""
        import src.updater as mod
        mod._CACHE_DIR = tmp_path
        mod._LAST_COOKIE_REFRESH = tmp_path / "LAST_COOKIE_REFRESH"

        config = MagicMock()
        config.cookies_file_path = tmp_path / "cookies.txt"
        config.get.return_value = "auto"

        cookies_tmp = config.cookies_file_path.with_suffix(".tmp")

        def _fake_run(cmd, **kw):
            assert "--cookies-from-browser" in cmd
            idx = cmd.index("--cookies-from-browser")
            assert cmd[idx + 1] == "firefox"
            cookies_tmp.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
            )
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=_fake_run):
            result = mod.refresh_cookies(config, verbose=False, browser="firefox")

        assert result is True

    def test_auto_detection_used_when_config_is_auto(self, tmp_path):
        """When config.browser is 'auto', detection should run."""
        import src.updater as mod
        mod._CACHE_DIR = tmp_path
        mod._LAST_COOKIE_REFRESH = tmp_path / "LAST_COOKIE_REFRESH"

        config = MagicMock()
        config.cookies_file_path = tmp_path / "cookies.txt"
        config.get.return_value = "auto"

        cookies_tmp = config.cookies_file_path.with_suffix(".tmp")

        def _fake_run(cmd, **kw):
            cookies_tmp.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
            )
            return MagicMock(returncode=0)

        fake_detected = [{"name": "brave", "label": "Brave"}]
        with patch("subprocess.run", side_effect=_fake_run), \
             patch("src.browsers.detect_installed_browsers", return_value=fake_detected):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is True

    def test_no_browsers_detected_returns_false(self, tmp_path):
        """When no browsers are found and config is 'auto', refresh should fail."""
        import src.updater as mod
        mod._CACHE_DIR = tmp_path
        mod._LAST_COOKIE_REFRESH = tmp_path / "LAST_COOKIE_REFRESH"

        config = MagicMock()
        config.cookies_file_path = tmp_path / "cookies.txt"
        config.get.return_value = "auto"

        with patch("src.browsers.detect_installed_browsers", return_value=[]):
            result = mod.refresh_cookies(config, verbose=False)

        assert result is False
