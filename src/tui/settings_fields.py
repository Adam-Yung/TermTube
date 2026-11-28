"""The Settings screen's rows: what each setting is called, how it is read, and how a typed value is validated."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from src.config import MAX_ROWS_PER_PAGE, MIN_ROWS_PER_PAGE, Config
from src.downloads import check_template
from src.strings import text as t

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
            return t("settings_fields.on") if value else t("settings_fields.off")
        if isinstance(value, list):
            return ", ".join(value)
        return "" if value is None else str(value)


def parse_dir(text: str) -> str:
    """A directory downloads can be written to: it exists and is writable, or can be created under one that is."""
    text = text.strip()
    if not text:
        raise Refused(t("settings_fields.dir_empty"))
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise Refused(t("settings_fields.dir_relative"))
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        raise Refused(t("settings_fields.dir_is_file", path=probe))
    if not os.access(probe, os.W_OK | os.X_OK):
        raise Refused(t("settings_fields.dir_not_writable", path=probe))
    return text


def parse_template(text: str) -> str:
    text = text.strip()
    try:
        check_template(text)
    except RuntimeError:
        raise Refused(t("settings_fields.template_invalid")) from None
    return text


def _parse_bounded(low: int, high: int, unit: str, text: str) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise Refused(t("settings_fields.int_not_number")) from None
    if not low <= value <= high:
        raise Refused(t("settings_fields.int_range", low=low, high=high, unit=unit))
    return value


def parse_int(low: int, high: int, unit: str = "") -> Callable[[str], int]:
    return partial(_parse_bounded, low, high, unit)


def parse_categories(text: str) -> list[str]:
    cats = [c.strip() for c in text.replace(",", " ").split()]
    if not cats:
        raise Refused(t("settings_fields.categories_empty"))
    unknown = [c for c in cats if c not in SB_CATEGORIES]
    if unknown:
        known = ", ".join(SB_CATEGORIES)
        raise Refused(t("settings_fields.categories_unknown", unknown=", ".join(unknown), known=known))
    return list(dict.fromkeys(cats))


def browser_status(config: Config) -> str:
    browser = config.resolved_browser()
    if browser:
        return t("settings_fields.browser_in_use", browser=browser)
    if str(config.get("browser", "auto")).lower() == "none":
        return t("settings_fields.browser_none")
    return t("settings_fields.browser_missing")


_SECTION_IDS = ("playback", "downloads", "data", "account", "display", "config_file")
SECTIONS = tuple(t(f"settings_fields.section_{name}") for name in _SECTION_IDS)
PLAYBACK, DOWNLOADS, DATA, ACCOUNT, DISPLAY, CONFIG_FILE = SECTIONS

THEME_OPTS = [(name, t(f"settings_fields.theme_{name}")) for name in ("crimson", "amber", "ocean", "midnight")]
QUALITY_OPTS = [(name, t(f"settings_fields.quality_{name}")) for name in ("best", "1080", "720", "480", "360")]
THUMB_OPTS = [(name, t(f"settings_fields.thumb_{name}")) for name in ("auto", "symbols")]


def _field(key: str, kind: str, section: str, read: Callable[[Config], object] | None = None, *,
           parse: Callable[[str], object] | None = None, options: list[tuple[str, str]] | None = None,
           note: bool = False) -> Field:
    """A ``Field`` whose label (and, with ``note=True``, note) is looked up in strings.json by its key."""
    name = key.replace(".", "_")
    return Field(
        key, t(f"settings_fields.field_{name}"), kind, section, read, options=options or [], parse=parse,
        note=t(f"settings_fields.note_{name}") if note else "",
    )


def _ttl(name: str, label: str) -> Field:
    return Field(
        f"cache_ttl.{name}", t("settings_fields.ttl_label", name=label), "int", DATA,
        lambda c: c.cache_ttl(name), parse=parse_int(MIN_TTL, MAX_TTL, t("settings_fields.seconds_unit")),
        note=t("settings_fields.seconds_note"),
    )


FIELDS: list[Field] = [
    _field("sponsorblock.enabled", "bool", PLAYBACK, lambda c: c.sponsorblock_enabled),
    _field("sponsorblock.categories", "text", PLAYBACK, lambda c: c.sponsorblock_categories,
          parse=parse_categories, note=True),
    _field("sponsorblock.auto_skip", "bool", PLAYBACK, lambda c: c.sponsorblock_auto_skip),
    _field("prefetch_video", "bool", PLAYBACK, lambda c: c.prefetch_video_enabled),
    _field("resume_playback", "bool", PLAYBACK, lambda c: c.resume_playback_enabled,
          note=True),

    _field("video_dir", "text", DOWNLOADS, lambda c: c.get("video_dir"), parse=parse_dir),
    _field("audio_dir", "text", DOWNLOADS, lambda c: c.get("audio_dir"), parse=parse_dir),
    _field("video_format", "text", DOWNLOADS, lambda c: c.video_format, parse=parse_template),
    _field("audio_format", "text", DOWNLOADS, lambda c: c.audio_format, parse=parse_template),
    _field("preferred_quality", "choice", DOWNLOADS, lambda c: c.preferred_quality,
          options=QUALITY_OPTS),

    _field("history", "bool", DATA, lambda c: c.history_enabled),
    _field("history_max", "int", DATA, lambda c: c.history_max,
          parse=parse_int(MIN_HISTORY, MAX_HISTORY), note=True),
    _field("search_history", "bool", DATA, lambda c: c.search_history_enabled),
    _field("search_suggestions", "bool", DATA, lambda c: c.search_suggestions_enabled,
          note=True),
    _ttl("home", t("settings_fields.ttl_home")),
    _ttl("search", t("settings_fields.ttl_search")),
    _ttl("metadata", t("settings_fields.ttl_metadata")),
    _field("clear_cache", "action", DATA),
    _field("clear_history", "action", DATA),
    _field("clear_search_history", "action", DATA),

    _field("browser", "choice", ACCOUNT, lambda c: c.get("browser", "auto")),
    _field("resolved_browser", "info", ACCOUNT, browser_status),
    _field("cookie_prewarm", "bool", ACCOUNT, lambda c: c.cookie_prewarm,
          note=True),

    _field("theme", "choice", DISPLAY, lambda c: c.theme, options=THEME_OPTS),
    _field("thumbnail_format", "choice", DISPLAY, lambda c: c.thumbnail_format,
          options=THUMB_OPTS),
    _field("rows_per_page", "int", DISPLAY, lambda c: c.rows_per_page,
          parse=parse_int(MIN_ROWS_PER_PAGE, MAX_ROWS_PER_PAGE), note=True),

    _field("reload", "action", CONFIG_FILE, note=True),
]
