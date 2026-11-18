"""User config (`~/.config/TermTube/config.yaml`) with defaults and validated accessors."""

from __future__ import annotations

from pathlib import Path

import yaml

from src import logger
from src.plat import get_config_dir

_DEFAULT_CONFIG_PATH = get_config_dir() / "config.yaml"
_THEMES = ("crimson", "amber", "ocean", "midnight")
_THUMBNAIL_FORMATS = ("auto", "symbols")
_DEFAULT_SB_CATEGORIES = ["sponsor", "selfpromo"]

DEFAULT_CONFIG: dict = {
    "browser": "auto",
    "video_dir": str(Path.home() / "Documents" / "TermTube" / "Video"),
    "audio_dir": str(Path.home() / "Documents" / "TermTube" / "Audio"),
    "video_format": "%(title)s_%(uploader)s.%(ext)s",
    "audio_format": "%(title)s_%(uploader)s.%(ext)s",
    "preferred_quality": "best",
    "cache_ttl": {
        "home": 3600,
        "subscriptions": 3600,
        "search": 1800,
        "metadata": 86400,
    },
    "thumbnail_format": "auto",
    "insecure_thumbnails": False,
    "theme": "crimson",
    "thumbnail_warning_dismissed": False,
    "sponsorblock": {
        "enabled": True,
        "auto_skip": True,
        "categories": list(_DEFAULT_SB_CATEGORIES),
    },
    "prefetch_video": False,
    "history": True,
    "history_max": 500,
    "search_history": True,
}


class Config:
    def __init__(self, path: str | None = None) -> None:
        self._data: dict = dict(DEFAULT_CONFIG)
        self._data["cache_ttl"] = dict(DEFAULT_CONFIG["cache_ttl"])
        self._data["sponsorblock"] = dict(DEFAULT_CONFIG["sponsorblock"])
        self.path = Path(path) if path else _DEFAULT_CONFIG_PATH

        self._load()
        if not self.path.exists():
            self.save()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        for section in ("cache_ttl", "sponsorblock"):
            if isinstance(loaded.get(section), dict):
                self._data[section].update(loaded.pop(section))
        self._data.update(loaded)
        self._data.pop("cookies_file", None)

    def browser_cookie_args(self) -> list[str]:
        """Return yt-dlp cookie flags for mpv passthrough (empty when browser is none)."""
        browser = self.get("browser", "auto")
        if not browser or browser.lower() == "none":
            return []
        from src.browsers import detect_installed_browsers, is_auto_browser
        if is_auto_browser(browser):
            detected = detect_installed_browsers()
            browser = detected[0]["name"] if detected else None
        if browser:
            return ["--cookies-from-browser", browser]
        return []

    @property
    def browser(self) -> str:
        return self._data.get("browser", "auto")

    @property
    def video_dir(self) -> Path:
        return Path(self._data["video_dir"]).expanduser()

    @property
    def audio_dir(self) -> Path:
        return Path(self._data["audio_dir"]).expanduser()

    @property
    def video_format(self) -> str:
        return self._data["video_format"]

    @property
    def audio_format(self) -> str:
        return self._data["audio_format"]

    @property
    def preferred_quality(self) -> str:
        return str(self._data.get("preferred_quality", "best"))

    @property
    def thumbnail_format(self) -> str:
        fmt = self._data.get("thumbnail_format", "auto")
        return fmt if fmt in _THUMBNAIL_FORMATS else "auto"

    @property
    def insecure_thumbnails(self) -> bool:
        """True only for a literal ``true``; a quoted or malformed value stays off."""
        return self._data.get("insecure_thumbnails") is True

    @property
    def theme(self) -> str:
        t = self._data.get("theme", "crimson")
        return t if t in _THEMES else "crimson"

    @property
    def history_enabled(self) -> bool:
        """False only for a literal ``false``: a typo must not silently stop recording."""
        return self._data.get("history") is not False

    @property
    def search_history_enabled(self) -> bool:
        return self._data.get("search_history") is not False

    @property
    def history_max(self) -> int:
        value = self._data.get("history_max")
        if isinstance(value, bool) or not isinstance(value, int):
            return 500
        return min(5000, max(50, value))

    @property
    def sponsorblock_enabled(self) -> bool:
        return bool(self._data.get("sponsorblock", {}).get("enabled", True))

    @property
    def sponsorblock_auto_skip(self) -> bool:
        return bool(self._data.get("sponsorblock", {}).get("auto_skip", True))

    @property
    def sponsorblock_categories(self) -> list[str]:
        cats = self._data.get("sponsorblock", {}).get("categories")
        if isinstance(cats, list):
            return cats
        return list(_DEFAULT_SB_CATEGORIES)

    def save(self) -> None:
        """Merge current values into the file on disk, preserving unknown keys. Failures are logged, not raised."""
        try:
            existing: dict = {}
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            existing.update({k: v for k, v in self._data.items()
                             if k not in ("cache_ttl", "sponsorblock")})
            existing["cache_ttl"] = self._data["cache_ttl"]
            existing["sponsorblock"] = self._data["sponsorblock"]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            logger.warning("Config.save() failed: %s (path=%s)", exc, self.path)

    def cache_ttl(self, key: str) -> int:
        return int(self._data["cache_ttl"].get(key, 3600))

    def __getitem__(self, key: str):
        return self._data[key]

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """Change a top-level setting in memory; ``save()`` persists it."""
        self._data[key] = value
