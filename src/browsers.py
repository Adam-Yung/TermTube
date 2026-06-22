"""Browser detection for cookie extraction.

Detects installed browsers that yt-dlp can extract cookies from.
Supports macOS, Windows, and Linux with zero external dependencies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from src.plat import IS_MACOS, IS_WINDOWS, IS_LINUX

# All browsers supported by yt-dlp's --cookies-from-browser
YTDLP_SUPPORTED_BROWSERS: list[str] = [
    "brave", "chrome", "chromium", "edge", "firefox",
    "opera", "safari", "vivaldi", "whale",
]

# Human-readable labels
_BROWSER_LABELS: dict[str, str] = {
    "brave": "Brave",
    "chrome": "Google Chrome",
    "chromium": "Chromium",
    "edge": "Microsoft Edge",
    "firefox": "Firefox",
    "opera": "Opera",
    "safari": "Safari",
    "vivaldi": "Vivaldi",
    "whale": "Naver Whale",
}

# macOS: .app bundle names in /Applications (and ~/Applications)
_MACOS_APP_BUNDLES: dict[str, str] = {
    "brave": "Brave Browser.app",
    "chrome": "Google Chrome.app",
    "chromium": "Chromium.app",
    "edge": "Microsoft Edge.app",
    "firefox": "Firefox.app",
    "opera": "Opera.app",
    "safari": "Safari.app",
    "vivaldi": "Vivaldi.app",
    "whale": "Whale.app",
}

# Windows: path components under Program Files / LocalAppData.
# Use tuples of path parts for cross-platform Path joining.
_WINDOWS_EXE_PARTS: dict[str, list[tuple[str, ...]]] = {
    "brave": [
        ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ],
    "chrome": [
        ("Google", "Chrome", "Application", "chrome.exe"),
    ],
    "chromium": [
        ("Chromium", "Application", "chrome.exe"),
    ],
    "edge": [
        ("Microsoft", "Edge", "Application", "msedge.exe"),
    ],
    "firefox": [
        ("Mozilla Firefox", "firefox.exe"),
    ],
    "opera": [
        ("Opera", "launcher.exe"),
        ("Opera", "opera.exe"),
    ],
    "vivaldi": [
        ("Vivaldi", "Application", "vivaldi.exe"),
    ],
    "whale": [
        ("Naver", "Naver Whale", "Application", "whale.exe"),
    ],
}

# Linux: yt-dlp looks for browser data dirs, but we check for executables on PATH
_LINUX_EXECUTABLES: dict[str, list[str]] = {
    "brave": ["brave-browser", "brave"],
    "chrome": ["google-chrome", "google-chrome-stable"],
    "chromium": ["chromium-browser", "chromium"],
    "edge": ["microsoft-edge", "microsoft-edge-stable"],
    "firefox": ["firefox"],
    "opera": ["opera"],
    "vivaldi": ["vivaldi", "vivaldi-stable"],
    "whale": ["whale", "naver-whale"],
}


def detect_installed_browsers() -> list[dict[str, str]]:
    """Detect browsers installed on this system that yt-dlp can extract cookies from.

    Returns a list of dicts with keys:
        - name: yt-dlp browser identifier (e.g. "chrome")
        - label: human-readable name (e.g. "Google Chrome")
    """
    if IS_MACOS:
        return _detect_macos()
    elif IS_WINDOWS:
        return _detect_windows()
    elif IS_LINUX:
        return _detect_linux()
    return []


def _detect_macos() -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    search_dirs = [Path("/Applications"), Path.home() / "Applications"]

    for name, bundle in _MACOS_APP_BUNDLES.items():
        for base in search_dirs:
            if (base / bundle).exists():
                found.append({"name": name, "label": _BROWSER_LABELS[name]})
                break

    return found


def _detect_windows() -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    search_roots: list[Path] = []
    for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        val = os.environ.get(env_var)
        if val:
            search_roots.append(Path(val))

    for name, parts_list in _WINDOWS_EXE_PARTS.items():
        detected = False
        for root in search_roots:
            for parts in parts_list:
                if (root / Path(*parts)).exists():
                    detected = True
                    break
            if detected:
                break
        if detected:
            found.append({"name": name, "label": _BROWSER_LABELS[name]})

    return found


def _detect_linux() -> list[dict[str, str]]:
    import shutil

    found: list[dict[str, str]] = []
    for name, executables in _LINUX_EXECUTABLES.items():
        for exe in executables:
            if shutil.which(exe):
                found.append({"name": name, "label": _BROWSER_LABELS[name]})
                break

    return found


def get_browser_label(name: str) -> str:
    """Return human-readable label for a browser name."""
    return _BROWSER_LABELS.get(name, name.title())


def is_auto_browser(value: str | None) -> bool:
    """Return True if the browser config value indicates auto-detection should run."""
    return value is None or value == "auto" or value == ""
