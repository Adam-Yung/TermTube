"""Configuration management for TermTube."""

from __future__ import annotations
from pathlib import Path
import yaml

_CONFIG_DIR = Path.home() / ".config" / "TermTube"
_DEFAULT_CONFIG_PATH = _CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG: dict = {
    "cookies_file": str(_CONFIG_DIR / "cookies.txt"),
    "browser": "chrome",
    "video_dir": str(Path.home() / "Documents" / "TermTube" / "Video"),
    "audio_dir": str(Path.home() / "Documents" / "TermTube" / "Audio"),
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
    # thumbnail_format: how chafa renders thumbnails in the Textual TUI.
    # "auto"    (default) = high-quality Unicode block/sextant art (best Textual-compatible mode).
    # "symbols"           = same as auto.
    # "ascii"             = restrict to ASCII-only symbols (most compatible fallback).
    # Note: sixel/kitty graphics protocols are incompatible with Textual's
    # cell-based renderer and are silently mapped to "symbols".
    "thumbnail_format": "auto",
    # theme: UI color theme. Options: crimson | amber | ocean | midnight
    "theme": "crimson",
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
        return _DEFAULT_CONFIG_PATH

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

    @property
    def thumbnail_format(self) -> str:
        fmt = self._data.get("thumbnail_format", "auto")
        return fmt if fmt in ("auto", "symbols", "sixel", "ascii") else "auto"

    @property
    def theme(self) -> str:
        t = self._data.get("theme", "crimson")
        return t if t in ("crimson", "amber", "ocean", "midnight") else "crimson"

    def save(self) -> None:
        """Persist current config back to disk (only user-visible keys)."""
        try:
            existing: dict = {}
            if self.path.exists():
                import yaml
                with open(self.path) as f:
                    existing = yaml.safe_load(f) or {}
            existing.update({k: v for k, v in self._data.items()
                             if k not in ("cache_ttl",)})
            existing["cache_ttl"] = self._data["cache_ttl"]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                import yaml
                yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        except Exception:
            pass

    def cache_ttl(self, key: str) -> int:
        return int(self._data["cache_ttl"].get(key, 3600))

    def __getitem__(self, key: str):
        return self._data[key]

    def get(self, key: str, default=None):
        return self._data.get(key, default)
