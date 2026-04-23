#!/usr/bin/env python3
"""
fzf preview script — called by fzf --preview for each focused item.

Usage: preview.py <video_id> [cols] [rows]

Reads cached metadata, downloads thumbnail if needed, renders with chafa.
Must be fast (< 1s ideally) — runs on every cursor movement in fzf.
"""

from __future__ import annotations
import sys
import json
import textwrap
from pathlib import Path

# Add project root to sys.path
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.cache import Cache, VIDEO_DIR, THUMB_DIR
from src.ui import thumbnail as thumb

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_YEL   = "\033[33m"
_GRN   = "\033[32m"
_GRAY  = "\033[90m"
_MAG   = "\033[35m"
_RED   = "\033[31m"
_BLU   = "\033[34m"
_BCYAN = "\033[96m"


def _fmt_views(n) -> str:
    if n is None:
        return ""
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def _fmt_duration(secs) -> str:
    if not secs:
        return "—"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_date(d: str) -> str:
    if d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or ""


def _sep(width: int, char: str = "─") -> str:
    return f"{_GRAY}{char * width}{_RESET}"


def _badge(text: str, color: str = _CYAN) -> str:
    return f"{color}[{text}]{_RESET}"


def render(video_id: str, cols: int, rows: int) -> None:
    # ── Load from cache (raw — ignores TTL so preview is always fast) ─────────
    path = VIDEO_DIR / f"{video_id}.json"
    if not path.exists():
        print(f"\n  {_GRAY}Loading…{_RESET}")
        return

    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        print(f"\n  {_RED}Cache read error{_RESET}")
        return

    is_flat = entry.get("description") is None  # True for flat-playlist entries

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    # YouTube thumbnails are 16:9. Terminal chars are ~2× taller than wide in
    # pixels (1:2 font ratio), so the natural row count for a full-width image is:
    #   natural_rows = cols * (9/16) / 2  =  cols * 9/32
    # This keeps the aspect ratio correct instead of squishing/stretching.
    thumb_cols = cols - 2
    natural_rows = max(8, int(thumb_cols * 9 / 32))
    thumb_rows = min(natural_rows, rows - 4)  # leave at least 4 rows for metadata
    thumb_art = thumb.render(video_id, entry, cols=thumb_cols, rows=thumb_rows)

    if thumb_art:
        print(thumb_art, end="")
    else:
        # Placeholder box in place of thumbnail
        print(f"\n  {_GRAY}{'░' * min(thumb_cols, 40)}{_RESET}")
        print()

    print(_sep(cols - 2))

    # ── Title ─────────────────────────────────────────────────────────────────
    title = entry.get("title") or "Untitled"
    effective_width = max(cols - 4, 20)
    title_lines = textwrap.wrap(title, width=effective_width)
    print()
    for line in title_lines[:2]:  # max 2 lines for title
        print(f"  {_BOLD}{line}{_RESET}")
    print()

    # ── Channel + stats ───────────────────────────────────────────────────────
    channel  = entry.get("channel") or entry.get("uploader") or ""
    date     = _fmt_date(entry.get("upload_date", ""))
    duration = _fmt_duration(entry.get("duration"))
    views    = _fmt_views(entry.get("view_count"))
    likes    = _fmt_views(entry.get("like_count")) if entry.get("like_count") else ""
    subs     = _fmt_views(entry.get("channel_follower_count")) if entry.get("channel_follower_count") else ""

    if channel:
        sub_str = f"  {_GRAY}({subs} subs){_RESET}" if subs else ""
        print(f"  {_CYAN}◉ {channel}{sub_str}{_RESET}")

    stat_parts = []
    if date:
        stat_parts.append(f"{_YEL}{date}{_RESET}")
    if duration != "—":
        stat_parts.append(f"{_GRN}⏱ {duration}{_RESET}")
    if views:
        stat_parts.append(f"{_GRAY}👁 {views}{_RESET}")
    if likes:
        stat_parts.append(f"{_MAG}👍 {likes}{_RESET}")

    if stat_parts:
        print("  " + f"  {_GRAY}·{_RESET}  ".join(stat_parts))

    # ── Status badge for flat entries ─────────────────────────────────────────
    if is_flat:
        print()
        print(f"  {_GRAY}⏳ Loading details…{_RESET}")

    print()

    # ── Description ───────────────────────────────────────────────────────────
    desc = entry.get("description") or entry.get("short_description") or ""
    if desc:
        print(_sep(cols - 2))
        print()
        desc_lines = desc.strip().splitlines()
        for line in desc_lines[:10]:
            if not line.strip():
                print()
                continue
            wrapped = textwrap.fill(line, width=effective_width, subsequent_indent="  ")
            print(f"  {_DIM}{wrapped}{_RESET}")
        if len(desc_lines) > 10:
            print(f"\n  {_GRAY}… (truncated){_RESET}")
        print()
    elif not is_flat:
        # Full fetch returned but no description
        print(f"  {_GRAY}(no description){_RESET}")
        print()

    # ── Tags ──────────────────────────────────────────────────────────────────
    tags = entry.get("tags") or []
    if tags:
        tag_line = "  ".join(f"{_GRAY}#{t}{_RESET}" for t in tags[:6])
        print(f"  {tag_line}")
        print()

    # ── Availability notice ───────────────────────────────────────────────────
    avail = entry.get("availability")
    if avail and avail != "public":
        print(f"  {_YEL}⚠ {avail}{_RESET}")
        print()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    video_id = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    render(video_id, cols, rows)


if __name__ == "__main__":
    main()
