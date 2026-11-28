"""The two-line Rich markup of a list row, per row type (video, playlist, channel)."""

from __future__ import annotations

import time

from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup, fmt_age, fmt_clock, fmt_duration, fmt_subscribers, fmt_views

_DL_BADGES = {
    "video": "badge_dl_video",
    "audio": "badge_dl_audio",
    "both": "badge_dl_both",
    "": "badge_dl_remote",
}
_SEP = "  [dim]·[/dim]  "


def row_markup(entry: Entry, theme_color: str, *, playing: bool = False, marked: bool = False) -> str:
    if entry.get("_is_channel"):
        return _channel_markup(entry, theme_color)
    return _video_markup(entry, theme_color, playing=playing, marked=marked)


def _two_lines(first: str, parts: list[str]) -> str:
    second = _SEP.join(p for p in parts if p)
    return f"{first}\n{second}" if second else first


def _channel_markup(entry: Entry, theme_color: str) -> str:
    name = (entry.get("channel") or entry.get("title") or entry.get("uploader")
            or text("video_list.channel_fallback"))
    if len(name) > 50:
        name = name[:47] + "..."
    subs = fmt_subscribers(entry.get("subscriber_count"))
    count = entry.get("video_count")
    parts = [
        text("video_list.subscribers", count=subs) if subs else "",
        text("video_list.videos", count=count) if count else "",
    ]
    first = f"[bold white]{escape_markup(name)}[/bold white] [{theme_color}]📺[/{theme_color}]"
    return _two_lines(first, [f"[dim]{p}[/dim]" if p else "" for p in parts])


def _video_markup(entry: Entry, theme_color: str, *, playing: bool, marked: bool) -> str:
    """A video or playlist row: marked dot, title and badge, then the metadata line."""
    title = entry.get("title") or text("video_list.untitled")
    if len(title) > 68:
        title = title[:65] + "…"
    mark = f"[bold {theme_color}]●[/bold {theme_color}] " if marked else ""
    key = _badge_key(entry, playing)
    badge = text(f"video_list.{key}") if key else ""
    first = f"{mark}[bold white]{escape_markup(title)}[/bold white]{badge}"
    return _two_lines(first, _meta_parts(entry, theme_color))


def _badge_key(entry: Entry, playing: bool) -> str:
    """The one badge a row shows, by priority; empty for none."""
    if playing:
        return "badge_playing"
    if entry.get("_missing_file"):
        return "badge_file_missing"
    if entry.get("_is_folder"):
        return "badge_folder"
    if entry.get("_is_playlist"):
        return "badge_playlist"
    if "_dl" in entry:
        return _DL_BADGES[entry["_dl"]]
    return _origin_badge_key(entry)


def _origin_badge_key(entry: Entry) -> str:
    local_type = entry.get("_local_type", "")
    if local_type == "video":
        return "badge_video_audio" if entry.get("_has_audio", False) else "badge_video"
    if local_type == "audio":
        return "badge_audio"
    return "badge_youtube" if entry.get("_yt") or entry.get("source") == "yt" else ""


def _meta_parts(entry: Entry, theme_color: str) -> list[str]:
    """The second line's fields in order; empty strings are the ones this row does not have."""
    channel = entry.get("uploader") or entry.get("channel") or ""
    count = entry.get("playlist_count") if entry.get("_is_playlist", False) else None
    duration = fmt_duration(entry.get("duration"))
    watched = _fmt_watched(entry.get("watched_at"))
    resume = entry.get("resume_s")
    plays = entry.get("plays") or 0
    plain = [
        duration,
        fmt_views(entry.get("view_count")),
        fmt_age(entry.get("upload_date")) or entry.get("published_text", ""),
    ]
    return [
        f"[{theme_color}]{escape_markup(channel)}[/{theme_color}]" if channel else "",
        f"[dim]{text('video_list.videos', count=count)}[/dim]" if count else "",
        *(f"[dim]{value}[/dim]" if value else "" for value in plain),
        f"[#6699cc]{watched}[/#6699cc]" if watched else "",
        f"[#6bff6b]▶ {fmt_clock(resume)} / {duration}[/#6bff6b]" if resume and entry.get("duration") else "",
        f"[dim]×{entry['plays']}[/dim]" if plays > 1 else "",
    ]


def _fmt_watched(ts: float | None) -> str:
    if not ts:
        return ""
    delta = time.time() - ts
    if delta < 60:
        return text("video_list.watched_now")
    if delta < 3600:
        return text("video_list.watched_minutes", count=int(delta / 60))
    if delta < 86400:
        return text("video_list.watched_hours", count=int(delta / 3600))
    if delta < 86400 * 30:
        return text("video_list.watched_days", count=int(delta / 86400))
    return text("video_list.watched_months", count=int(delta / (86400 * 30)))
