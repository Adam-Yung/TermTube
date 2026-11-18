"""Display formatters for durations, view counts and ages."""

from __future__ import annotations

import datetime
import re

from src.strings import text

_BACKSLASH_BEFORE_BRACKET = re.compile(r"\\(?=\[|\Z)")


def escape_markup(text: str) -> str:
    """Make ``text`` safe to embed in Rich/Textual markup. Titles and descriptions often contain ``[...]``.

    A backslash right before a bracket (or at the end, where the template's next tag follows) would escape that
    bracket and swallow the tag, and markup cannot spell a literal one there: a zero-width space keeps them apart.
    """
    return _BACKSLASH_BEFORE_BRACKET.sub(lambda m: "\\\u200b", text).replace("[", "\\[")


def fmt_clock(secs: int | float) -> str:
    """Format seconds as H:MM:SS or M:SS; zero is ``0:00``."""
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_duration(secs: int | float | None) -> str:
    """``fmt_clock`` for a video length; empty when the length is unknown or zero."""
    return fmt_clock(secs) if secs else ""


def fmt_views(n: int | None) -> str:
    """Format a view count compactly (e.g. 1.2M views)."""
    if not n:
        return ""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B views"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K views"
    return f"{n} views"


def fmt_breadcrumb(parts: list[str], max_len: int = 70) -> str:
    """``Home › Chan › Playlists``. Too long: the first part, ``…`` and the last two remain."""
    text = " › ".join(parts)
    if len(text) > max_len and len(parts) > 3:
        text = " › ".join([parts[0], "…", *parts[-2:]])
    return text if len(text) <= max_len else "…" + text[-(max_len - 1):]


def fmt_subscribers(n: int | None) -> str:
    """Format a subscriber count compactly (e.g. 1.2M, 340K); the caller adds the noun."""
    if not n:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def fmt_age(upload_date: str | None) -> str:
    """Format a YYYYMMDD upload date as a relative age string."""
    if not upload_date or len(upload_date) < 8:
        return ""
    try:
        y, m, d = int(upload_date[:4]), int(upload_date[4:6]), int(upload_date[6:8])
        delta = datetime.date.today() - datetime.date(y, m, d)
        days = delta.days
        if days < 0:
            return ""
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days}d ago"
        if days < 30:
            return f"{days // 7}w ago"
        if days < 365:
            return f"{days // 30}mo ago"
        return f"{days // 365}y ago"
    except (ValueError, TypeError):
        return ""


def fmt_day_group(ts: float | None, today: datetime.date | None = None) -> str:
    """Day header for a history row: Today, Yesterday, `Mon 9 Nov` (with the year when not this year)."""
    if not ts:
        return text("fmt.day_earlier")
    today = today or datetime.date.today()
    day = datetime.date.fromtimestamp(ts)
    if day == today:
        return text("fmt.day_today")
    if day == today - datetime.timedelta(days=1):
        return text("fmt.day_yesterday")
    label = f"{day:%a} {day.day} {day:%b}"
    return label if day.year == today.year else f"{label} {day.year}"


def fmt_size(n: int | float | None) -> str:
    """Bytes as `812 KB`, `120 MB`, `1.4 GB`; empty when unknown."""
    if not n:
        return ""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if value >= 100 or unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return ""
