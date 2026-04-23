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


def _fmt_views(n) -> str:
    if n is None:
        return "?"
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
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_date(d: str) -> str:
    if d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or "—"


def _separator(char: str = "─", width: int = 52) -> str:
    return f"{_GRAY}{char * width}{_RESET}"


def _badge(text: str, color: str = _CYAN) -> str:
    return f"{color}[{text}]{_RESET}"


def render(video_id: str, cols: int, rows: int) -> None:
    # Load from cache (raw — ignores TTL so preview is always fast)
    path = VIDEO_DIR / f"{video_id}.json"
    if not path.exists():
        print(f"\n  {_GRAY}Loading…{_RESET}")
        return

    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        print(f"\n  {_RED}Cache read error{_RESET}")
        return

    # ── Thumbnail ─────────────────────────────────────────────────────────────
    thumb_art = thumb.render(video_id, entry, cols=cols, rows=rows)
    if thumb_art:
        print(thumb_art, end="")
    else:
        print(f"  {_GRAY}[no thumbnail]{_RESET}")

    print(_separator())

    # ── Title ─────────────────────────────────────────────────────────────────
    title = entry.get("title") or "Untitled"
    # Wrap long titles
    wrapped = textwrap.fill(title, width=cols - 2, subsequent_indent="  ")
    print(f"\n  {_BOLD}{wrapped}{_RESET}\n")

    # ── Channel + stats ───────────────────────────────────────────────────────
    channel  = entry.get("channel") or entry.get("uploader") or ""
    date     = _fmt_date(entry.get("upload_date", ""))
    duration = _fmt_duration(entry.get("duration"))
    views    = _fmt_views(entry.get("view_count"))
    likes    = entry.get("like_count")

    if channel:
        print(f"  {_CYAN}▶ {channel}{_RESET}")

    stats_parts = []
    if date:
        stats_parts.append(f"{_YEL}{date}{_RESET}")
    if duration:
        stats_parts.append(f"{_GRN}⏱ {duration}{_RESET}")
    if views:
        stats_parts.append(f"{_GRAY}👁 {views} views{_RESET}")
    if likes:
        stats_parts.append(f"{_MAG}👍 {_fmt_views(likes)}{_RESET}")

    if stats_parts:
        print("  " + "  │  ".join(stats_parts))

    print()

    # ── Description ───────────────────────────────────────────────────────────
    desc = entry.get("description") or entry.get("short_description") or ""
    if desc:
        print(_separator())
        print()
        # Trim very long descriptions for preview
        desc_lines = desc.strip().splitlines()[:12]
        for line in desc_lines:
            wrapped_line = textwrap.fill(line or " ", width=cols - 2, subsequent_indent="  ")
            print(f"  {_DIM}{wrapped_line}{_RESET}")
        if len(desc.splitlines()) > 12:
            print(f"\n  {_GRAY}… (full description in video view){_RESET}")
        print()

    # ── Tags ──────────────────────────────────────────────────────────────────
    tags = entry.get("tags") or []
    if tags:
        tag_line = "  ".join(f"{_GRAY}#{t}{_RESET}" for t in tags[:6])
        print(f"\n  {tag_line}\n")

    # ── Availability notice ───────────────────────────────────────────────────
    avail = entry.get("availability")
    if avail and avail != "public":
        print(f"  {_YEL}⚠ {avail}{_RESET}\n")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    video_id = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 38
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    render(video_id, cols, rows)


if __name__ == "__main__":
    main()
