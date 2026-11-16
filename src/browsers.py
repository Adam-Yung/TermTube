"""Detect installed browsers that yt-dlp can read cookies from."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from src.plat import IS_MACOS, IS_WINDOWS, IS_LINUX

YTDLP_SUPPORTED_BROWSERS: list[str] = [
    "brave", "chrome", "chromium", "edge", "firefox",
    "opera", "safari", "vivaldi", "whale",
]

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

# Order is detection priority: Firefox needs no keychain approval, Chromium-family does, Safari is sandboxed.
_MACOS_APP_BUNDLES: dict[str, str] = {
    "firefox": "Firefox.app",
    "brave": "Brave Browser.app",
    "chrome": "Google Chrome.app",
    "chromium": "Chromium.app",
    "edge": "Microsoft Edge.app",
    "opera": "Opera.app",
    "vivaldi": "Vivaldi.app",
    "whale": "Whale.app",
    "safari": "Safari.app",
}

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


def _entry(name: str) -> dict[str, str]:
    return {"name": name, "label": _BROWSER_LABELS[name]}


def detect_installed_browsers() -> list[dict[str, str]]:
    """Installed browsers as ``{"name": yt-dlp id, "label": display name}``, in detection priority order."""
    if IS_MACOS:
        return _detect_macos()
    if IS_WINDOWS:
        return _detect_windows()
    if IS_LINUX:
        return _detect_linux()
    return []


def _detect_macos() -> list[dict[str, str]]:
    search_dirs = [Path("/Applications"), Path.home() / "Applications"]
    return [
        _entry(name)
        for name, bundle in _MACOS_APP_BUNDLES.items()
        if any((base / bundle).exists() for base in search_dirs)
    ]


def _detect_windows() -> list[dict[str, str]]:
    roots = [
        Path(val)
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
        if (val := os.environ.get(env_var))
    ]
    return [
        _entry(name)
        for name, parts_list in _WINDOWS_EXE_PARTS.items()
        if any((root / Path(*parts)).exists() for root in roots for parts in parts_list)
    ]


def _detect_linux() -> list[dict[str, str]]:
    return [
        _entry(name)
        for name, executables in _LINUX_EXECUTABLES.items()
        if any(shutil.which(exe) for exe in executables)
    ]


def get_browser_label(name: str) -> str:
    return _BROWSER_LABELS.get(name, name.title())


def is_auto_browser(value: str | None) -> bool:
    """True if the config value asks for auto-detection (None, empty or ``"auto"``)."""
    return value is None or value == "auto" or value == ""
