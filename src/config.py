"""TermTube v2 — configuration manager.

Reads/writes ~/.config/TermTube/config.yaml.
Auto-created with defaults on first run.
Backward-compatible with v1 config files.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path("~/.config/TermTube").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.yaml"
COOKIES_PATH = CONFIG_DIR / "cookies.txt"
HISTORY_PATH = CONFIG_DIR / "history.json"
PLAYLISTS_PATH = CONFIG_DIR / "playlists.json"
HIDDEN_PATH = CONFIG_DIR / "hidden.json"
SEARCH_HISTORY_PATH = CONFIG_DIR / "search_history.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # Paths
    "cookies_file": str(COOKIES_PATH),
    "video_dir": str(Path("~/Documents/TermTube/Video").expanduser()),
    "audio_dir": str(Path("~/Documents/TermTube/Audio").expanduser()),
    # Cookies
    "browser": "chrome",
    "cookie_max_age_days": 7,
    # Downloads
    "video_format": "%(title)s_%(uploader)s.%(ext)s",
    "audio_format": "%(title)s_%(uploader)s.%(ext)s",
    # Playback — best quality always as default
    "preferred_quality": "bestvideo+bestaudio/best",
    "preferred_audio_quality": "bestaudio/best",
    "volume_step": 5,
    # Paging
    "page_size": 20,
    # Thumbnails
    "thumbnail_cols": 38,
    "thumbnail_rows": 20,
    "thumbnail_in_list": True,
    # UI
    "theme": "crimson",
    "show_watched_indicator": True,
    # Search history
    "search_history_count": 20,
    # SponsorBlock
    "sponsorblock_enabled": False,
    "sponsorblock_categories": ["sponsor", "selfpromo"],
    # Cache TTLs (seconds)
    "cache_ttl": {
        "home": 3600,
        "subscriptions": 3600,
        "search": 1800,
        "metadata": 86400,
        "sponsorblock": 3600,
    },
    # Internal flags (not shown in settings UI)
    "thumbnail_warning_dismissed": False,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class Config:
    """Thin wrapper around the YAML config file."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._data["cache_ttl"] = dict(DEFAULT_CONFIG["cache_ttl"])
        self._loaded = False

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                user = yaml.safe_load(fh) or {}
            self._data = _deep_merge(DEFAULT_CONFIG, user)
        else:
            self.save()
        self._loaded = True

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Only write user-visible keys (omit internal flags that have been
        # merged in from DEFAULT_CONFIG but were never set by the user).
        out: dict[str, Any] = {
            k: v for k, v in self._data.items()
            if k != "thumbnail_warning_dismissed"
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(out, fh, default_flow_style=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Property access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"Config has no key {name!r}")

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def cookies_file(self) -> Path:
        return Path(self._data["cookies_file"]).expanduser()

    @property
    def video_dir(self) -> Path:
        return Path(self._data["video_dir"]).expanduser()

    @property
    def audio_dir(self) -> Path:
        return Path(self._data["audio_dir"]).expanduser()

    @property
    def cookie_args(self) -> list[str]:
        """Return yt-dlp cookie CLI args, preferring cookies.txt file."""
        p = self.cookies_file
        if p.exists():
            return ["--cookies", str(p)]
        browser = self._data.get("browser", "chrome")
        if browser:
            return ["--cookies-from-browser", browser]
        return []

    @property
    def ydl_cookie_opts(self) -> dict[str, Any]:
        """Return yt-dlp Python API cookie opts dict."""
        p = self.cookies_file
        if p.exists():
            return {"cookiefile": str(p)}
        browser = self._data.get("browser", "chrome")
        if browser:
            return {"cookiesfrombrowser": (browser,)}
        return {}

    @property
    def page_size(self) -> int:
        return int(self._data.get("page_size", 20))

    @property
    def volume_step(self) -> int:
        return int(self._data.get("volume_step", 5))

    @property
    def cookie_max_age_days(self) -> int:
        return int(self._data.get("cookie_max_age_days", 7))

    @property
    def sponsorblock_enabled(self) -> bool:
        return bool(self._data.get("sponsorblock_enabled", False))

    @property
    def sponsorblock_categories(self) -> list[str]:
        return list(self._data.get("sponsorblock_categories", ["sponsor", "selfpromo"]))

    @property
    def cache_ttl(self) -> dict[str, int]:
        return dict(self._data.get("cache_ttl", DEFAULT_CONFIG["cache_ttl"]))

    def ttl(self, key: str) -> int:
        return int(self.cache_ttl.get(key, 3600))

    def persist_browser(self, browser: str) -> None:
        """Save browser choice immediately (called after successful cookie refresh)."""
        self._data["browser"] = browser
        self.save()
