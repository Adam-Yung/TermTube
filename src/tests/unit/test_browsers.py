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

