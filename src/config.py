"""Configuration management for MyYouTube."""

from __future__ import annotations
from pathlib import Path
import yaml

# Resolved at import time relative to project root
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "MyYouTube.yaml"
_XDG_CONFIG_PATH = Path.home() / ".config" / "myyoutube" / "config.yaml"

DEFAULT_CONFIG: dict = {
    "cookies_file": str(Path.home() / "Documents" / "MyYouTube" / "cookies.txt"),
    "browser": "chrome",
    "video_dir": str(Path.home() / "Documents" / "MyYouTube" / "Video"),
    "audio_dir": str(Path.home() / "Documents" / "MyYouTube" / "Audio"),
    "video_format": "%(title)s_%(uploader)s.%(ext)s",
    "audio_format": "%(title)s_%(uploader)s.%(ext)s",
    "preferred_quality": "best",
    "preferred_player": "mpv",
    "cache_ttl": {
        "home": 3600,
        "subscriptions": 3600,
        "search": 1800,
        "metadata": 86400,
    },
    "thumbnail_cols": 38,
    "thumbnail_rows": 20,
}


class Config:
    def __init__(self, path: str | None = None) -> None:
        self._data: dict = dict(DEFAULT_CONFIG)
        self._data["cache_ttl"] = dict(DEFAULT_CONFIG["cache_ttl"])

        if path:
            self.path = Path(path)
        else:
            self.path = self._find_config()

        self._load()

    # ── Discovery ────────────────────────────────────────────────────────────

    def _find_config(self) -> Path:
        if _DEFAULT_CONFIG_PATH.exists():
            return _DEFAULT_CONFIG_PATH
        if _XDG_CONFIG_PATH.exists():
            return _XDG_CONFIG_PATH
        return _DEFAULT_CONFIG_PATH  # will be created on first save if needed

    def _load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path) as f:
            loaded = yaml.safe_load(f) or {}
        # Deep merge cache_ttl
        if "cache_ttl" in loaded and isinstance(loaded["cache_ttl"], dict):
            self._data["cache_ttl"].update(loaded["cache_ttl"])
            loaded.pop("cache_ttl")
        self._data.update(loaded)

    # ── Cookie resolution (priority: file → browser) ─────────────────────────

    @property
    def cookie_args(self) -> list[str]:
        """Return yt-dlp cookie flags based on config priority."""
        cf = self.cookies_file
        if cf and cf.exists():
            return ["--cookies", str(cf)]
        if self._data.get("browser"):
            return ["--cookies-from-browser", self._data["browser"]]
        return []

    @property
    def cookies_file(self) -> Path | None:
        raw = self._data.get("cookies_file")
        if not raw:
            return None
        p = Path(raw).expanduser()
        return p if p.exists() else None

    @property
    def cookies_file_path(self) -> Path | None:
        """Configured path even if it doesn't exist yet (for display)."""
        raw = self._data.get("cookies_file")
        return Path(raw).expanduser() if raw else None

    @property
    def cookie_source(self) -> str:
        """Human-readable description of the active cookie source."""
        cf = self.cookies_file
        if cf:
            return f"cookies.txt ({cf})"
        browser = self._data.get("browser")
        if browser:
            return f"{browser} browser"
        return "none (unauthenticated)"

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def browser(self) -> str:
        return self._data.get("browser", "chrome")

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
    def preferred_player(self) -> str:
        return self._data.get("preferred_player", "mpv")

    @property
    def thumbnail_cols(self) -> int:
        return int(self._data.get("thumbnail_cols", 38))

    @property
    def thumbnail_rows(self) -> int:
        return int(self._data.get("thumbnail_rows", 20))

    def cache_ttl(self, key: str) -> int:
        return int(self._data["cache_ttl"].get(key, 3600))

    def __getitem__(self, key: str):
        return self._data[key]

    def get(self, key: str, default=None):
        return self._data.get(key, default)
