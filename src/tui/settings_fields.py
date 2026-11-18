"""The Settings screen's rows: what each setting is called, how it is read, and how a typed value is validated."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.config import MAX_ROWS_PER_PAGE, MIN_ROWS_PER_PAGE, Config
from src.downloads import check_template

SB_CATEGORIES = (
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic", "poi_highlight",
)
MIN_HISTORY, MAX_HISTORY = 50, 5000
MIN_TTL, MAX_TTL = 60, 30 * 86400


class Refused(ValueError):
    """A typed value was rejected; the message is the one-line reason shown to the user."""


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str  # bool | choice | text | int | action
    section: str
    read: Callable[[Config], object] | None = None
    options: list[tuple[str, str]] = field(default_factory=list)
    parse: Callable[[str], object] | None = None
    note: str = ""

    def show(self, config: Config) -> str:
        value = self.read(config) if self.read else None
        if self.kind == "bool":
            return "on" if value else "off"
        if isinstance(value, list):
            return ", ".join(value)
        return "" if value is None else str(value)


def parse_dir(text: str) -> str:
    """A directory downloads can be written to: it exists and is writable, or can be created under one that is."""
    text = text.strip()
    if not text:
        raise Refused("enter a directory")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise Refused("use an absolute path (or start with ~)")
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        raise Refused(f"{probe} is a file, not a directory")
    if not os.access(probe, os.W_OK | os.X_OK):
        raise Refused(f"{probe} is not writable")
    return text


def parse_template(text: str) -> str:
    text = text.strip()
    try:
        check_template(text)
    except RuntimeError:
        raise Refused("use a relative path without '..' (no leading / or drive letter)") from None
    return text


def parse_int(low: int, high: int, unit: str = "") -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text.strip())
        except ValueError:
            raise Refused("enter a whole number") from None
        if not low <= value <= high:
            raise Refused(f"enter a number from {low} to {high}{unit}")
        return value
    return parse


def parse_categories(text: str) -> list[str]:
    cats = [c.strip() for c in text.replace(",", " ").split()]
    if not cats:
        raise Refused("name at least one category")
    unknown = [c for c in cats if c not in SB_CATEGORIES]
    if unknown:
        raise Refused(f"unknown: {', '.join(unknown)}. Known: {', '.join(SB_CATEGORIES)}")
    return list(dict.fromkeys(cats))


def browser_status(config: Config) -> str:
    browser = config.resolved_browser()
    if browser:
        return f"{browser} — cookies from this browser are used"
    if str(config.get("browser", "auto")).lower() == "none":
        return "none — signed out, no cookies"
    return "no supported browser found — no cookies"


SECTIONS = ("Playback", "Downloads", "Data", "Account", "Display", "Config file")

THEME_OPTS = [
    ("crimson",  "🔴  Crimson   — deep red accents (default)"),
    ("amber",    "🟠  Amber     — warm orange"),
    ("ocean",    "🔵  Ocean     — cool teal / cyan"),
    ("midnight", "🟣  Midnight  — soft purple"),
]
QUALITY_OPTS = [
    ("best",  "best  — highest available"),
    ("1080",  "1080p — Full HD"),
    ("720",   "720p  — HD"),
    ("480",   "480p  — SD"),
    ("360",   "360p  — low"),
]
THUMB_OPTS = [
    ("auto",    "auto    — real image if supported (default)"),
    ("symbols", "symbols — always Unicode block art"),
]


def _ttl(name: str, label: str) -> Field:
    return Field(
        f"cache_ttl.{name}", f"Cache TTL: {label}", "int", "Data",
        lambda c: c.cache_ttl(name), parse=parse_int(MIN_TTL, MAX_TTL, " seconds"), note="seconds",
    )


FIELDS: list[Field] = [
    Field("sponsorblock.enabled", "SponsorBlock", "bool", "Playback", lambda c: c.sponsorblock_enabled),
    Field("sponsorblock.categories", "Skip categories", "text", "Playback", lambda c: c.sponsorblock_categories,
          parse=parse_categories, note="comma separated"),
    Field("sponsorblock.auto_skip", "Auto-skip segments", "bool", "Playback", lambda c: c.sponsorblock_auto_skip),
    Field("prefetch_video", "Prefetch video stream", "bool", "Playback", lambda c: c.prefetch_video_enabled),
    Field("resume_playback", "Resume where you stopped", "bool", "Playback", lambda c: c.resume_playback_enabled,
          note="History rows with a saved position start there"),

    Field("video_dir", "Video folder", "text", "Downloads", lambda c: c.get("video_dir"), parse=parse_dir),
    Field("audio_dir", "Audio folder", "text", "Downloads", lambda c: c.get("audio_dir"), parse=parse_dir),
    Field("video_format", "Video file name", "text", "Downloads", lambda c: c.video_format, parse=parse_template),
    Field("audio_format", "Audio file name", "text", "Downloads", lambda c: c.audio_format, parse=parse_template),
    Field("preferred_quality", "Preferred quality", "choice", "Downloads", lambda c: c.preferred_quality,
          options=QUALITY_OPTS),

    Field("history", "Watch history", "bool", "Data", lambda c: c.history_enabled),
    Field("history_max", "History size", "int", "Data", lambda c: c.history_max,
          parse=parse_int(MIN_HISTORY, MAX_HISTORY), note="entries"),
    Field("search_history", "Search history", "bool", "Data", lambda c: c.search_history_enabled),
    Field("search_suggestions", "Search suggestions", "bool", "Data", lambda c: c.search_suggestions_enabled,
          note="partial text goes to Google"),
    _ttl("home", "Home"),
    _ttl("search", "Search"),
    _ttl("metadata", "Video metadata"),
    Field("clear_cache", "Clear cache", "action", "Data"),
    Field("clear_history", "Clear watch history", "action", "Data"),
    Field("clear_search_history", "Clear search history", "action", "Data"),

    Field("browser", "Browser", "choice", "Account", lambda c: c.get("browser", "auto")),
    Field("resolved_browser", "In use", "info", "Account", browser_status),
    Field("cookie_prewarm", "Read browser session at startup", "bool", "Account", lambda c: c.cookie_prewarm,
          note="warms the Home feed; never when the browser is none"),

    Field("theme", "Theme", "choice", "Display", lambda c: c.theme, options=THEME_OPTS),
    Field("thumbnail_format", "Thumbnail format", "choice", "Display", lambda c: c.thumbnail_format,
          options=THUMB_OPTS),
    Field("rows_per_page", "Rows per page", "int", "Display", lambda c: c.rows_per_page,
          parse=parse_int(MIN_ROWS_PER_PAGE, MAX_ROWS_PER_PAGE), note="applies at the next list load"),

    Field("reload", "Reload from disk", "action", "Config file", note="re-read config.yaml after editing it by hand"),
]
