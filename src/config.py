"""User config (`~/.config/TermTube/config.yaml`) with defaults and validated accessors."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from src import logger
from src.plat import get_config_dir

_DEFAULT_CONFIG_PATH = get_config_dir() / "config.yaml"
_THEMES = ("crimson", "amber", "ocean", "midnight")
_THUMBNAIL_FORMATS = ("auto", "symbols")
_DEFAULT_SB_CATEGORIES = ["sponsor", "selfpromo"]
_SECTIONS = ("cache_ttl", "sponsorblock")
MIN_ROWS_PER_PAGE, DEFAULT_ROWS_PER_PAGE, MAX_ROWS_PER_PAGE = 10, 20, 50

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
        "yt_history": 600,
        "yt_watchlater": 600,
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
    "cookie_prewarm": True,
    "prefetch_video": False,
    "rows_per_page": DEFAULT_ROWS_PER_PAGE,
    "history": True,
    "history_max": 500,
    "search_history": True,
    "search_suggestions": True,
}


class Config:
    def __init__(self, path: str | None = None) -> None:
        self._data: dict = {section: {} for section in _SECTIONS}
        self.path = Path(path) if path else _DEFAULT_CONFIG_PATH

        self._apply(self._read())
        if not self.path.exists():
            self.save()

    def _read(self) -> dict:
        """The file's settings; ``{}`` when it does not exist. Raises OSError, ValueError or yaml.YAMLError."""
        if not self.path.exists():
            return {}
        with open(self.path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            raise ValueError("the file must hold a mapping of settings")
        return loaded

    def _apply(self, loaded: dict) -> None:
        """Replace every setting with defaults overlaid by ``loaded``.

        The two nested sections are updated in place: ``Cache`` holds ``cache_ttl`` by reference.
        """
        data = dict(DEFAULT_CONFIG)
        for section in _SECTIONS:
            data[section] = copy.deepcopy(DEFAULT_CONFIG[section])
            if isinstance(loaded.get(section), dict):
                data[section].update(loaded[section])
        data.update({k: v for k, v in loaded.items() if k not in _SECTIONS})
        data.pop("cookies_file", None)
        for section in _SECTIONS:
            self._data[section].clear()
            self._data[section].update(data.pop(section))
        for key in [k for k in self._data if k not in _SECTIONS]:
            del self._data[key]
        self._data.update(data)

    def reload(self) -> str | None:
        """Re-read the file. None on success; else a one-line reason, and the settings in memory stay as they were."""
        try:
            loaded = self._read()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            return (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        if not self.path.exists():
            return "the file does not exist"
        self._apply(loaded)
        return None
    def resolved_browser(self) -> str | None:
        """The browser whose cookies are used (``auto`` = first detected); None for ``none`` or nothing found."""
        browser = self.get("browser", "auto")
        if not browser or browser.lower() == "none":
            return None
        from src.browsers import detect_installed_browsers, is_auto_browser
        if is_auto_browser(browser):
            detected = detect_installed_browsers()
            return detected[0]["name"] if detected else None
        return browser

    def browser_cookie_args(self) -> list[str]:
        """Return yt-dlp cookie flags for mpv passthrough (empty when no browser resolves)."""
        browser = self.resolved_browser()
        return ["--cookies-from-browser", browser] if browser else []

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
    def search_suggestions_enabled(self) -> bool:
        """On unless a literal ``false``: partial search text goes to Google while typing, so this is the opt-out."""
        return self._data.get("search_suggestions") is not False

    @property
    def history_max(self) -> int:
        value = self._data.get("history_max")
        if isinstance(value, bool) or not isinstance(value, int):
            return 500
        return min(5000, max(50, value))

    @property
    def rows_per_page(self) -> int:
        value = self._data.get("rows_per_page")
        if isinstance(value, bool) or not isinstance(value, int):
            return DEFAULT_ROWS_PER_PAGE
        return min(MAX_ROWS_PER_PAGE, max(MIN_ROWS_PER_PAGE, value))

    @property
    def cookie_prewarm(self) -> bool:
        """Read the browser cookies in the background after first paint; only a literal ``false`` turns it off."""
        return self._data.get("cookie_prewarm") is not False

    @property
    def prefetch_video_enabled(self) -> bool:
        """True only for a literal ``true``; it costs a second stream resolve per focused row."""
        return self._data.get("prefetch_video") is True

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

    def save(self) -> bool:
        """Merge current values into the file on disk, preserving unknown keys. Failures are logged, not raised.

        Returns False when nothing was written (read-only path, unparsable file on disk).
        """
        try:
            existing: dict = {}
            if self.path.exists():
                with open(self.path, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            existing.update({k: v for k, v in self._data.items() if k not in _SECTIONS})
            for section in _SECTIONS:
                existing[section] = self._data[section]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            logger.warning("Config.save() failed: %s (path=%s)", exc, self.path)
            return False
        return True

    def cache_ttl(self, key: str) -> int:
        value = self._data["cache_ttl"].get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else 3600

    def __getitem__(self, key: str):
        return self._data[key]

    def get(self, key: str, default=None):
        """Raw value; ``section.name`` reaches into ``cache_ttl`` and ``sponsorblock``. Not validated."""
        container, name = _slot_in(self._data, key)
        return container.get(name, default)

    def set(self, key: str, value) -> None:
        """Change a setting in memory (dotted keys reach ``sponsorblock`` and ``cache_ttl``); ``save()`` persists it."""
        container, name = _slot_in(self._data, key)
        container[name] = value

    def reset(self, key: str) -> None:
        """Put one setting back to its default, in memory."""
        container, name = _slot_in(DEFAULT_CONFIG, key)
        self.set(key, copy.deepcopy(container[name]))


def _slot_in(data: dict, key: str) -> tuple[dict, str]:
    section, _, name = key.partition(".")
    if name and section in _SECTIONS:
        return data[section], name
    return data, key
