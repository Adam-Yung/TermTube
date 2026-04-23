"""Video detail page — full info + action menu for a single video."""

from __future__ import annotations
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from src import history, library
from src.ui import gum, thumbnail as thumb
from src import player as mpv_player
from src import ytdlp

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_YEL   = "\033[33m"
_GRN   = "\033[32m"
_GRAY  = "\033[90m"
_MAG   = "\033[35m"
_RED   = "\033[31m"


def _sep(width: int = 60) -> str:
    return f"{_GRAY}{'─' * width}{_RESET}"


def _fmt_views(n) -> str:
    if n is None:
        return "—"
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
    return d or "—"


def _print_header(entry: dict, config) -> None:
    """Print thumbnail + metadata header."""
    os.system("clear")

    video_id = entry.get("id", "")
    cols = config.thumbnail_cols
    rows = config.thumbnail_rows

    # Thumbnail
    art = thumb.render(video_id, entry, cols=cols, rows=rows)
    if art:
        print(art, end="")
    else:
        print(f"\n  {_GRAY}[thumbnail unavailable]{_RESET}")

    print(_sep())
    print()

    # Title
    title = entry.get("title") or "Untitled"
    term_w = os.get_terminal_size().columns if sys.stdout.isatty() else 80
    wrapped = textwrap.fill(title, width=min(term_w - 4, 76), subsequent_indent="  ")
    print(f"  {_BOLD}{wrapped}{_RESET}")
    print()

    # Channel info
    channel = entry.get("channel") or entry.get("uploader") or ""
    channel_url = entry.get("channel_url") or entry.get("uploader_url") or ""
    subs = entry.get("channel_follower_count")
    if channel:
        sub_str = f"  {_GRAY}({_fmt_views(subs)} subscribers){_RESET}" if subs else ""
        print(f"  {_CYAN}◉ {channel}{sub_str}{_RESET}")

    # Stats row
    date     = _fmt_date(entry.get("upload_date", ""))
    duration = _fmt_duration(entry.get("duration"))
    views    = _fmt_views(entry.get("view_count"))
    likes    = entry.get("like_count")

    parts = []
    if date:     parts.append(f"{_YEL}📅 {date}{_RESET}")
    if duration: parts.append(f"{_GRN}⏱ {duration}{_RESET}")
    if views:    parts.append(f"{_GRAY}👁 {views} views{_RESET}")
    if likes:    parts.append(f"{_MAG}👍 {_fmt_views(likes)}{_RESET}")

    if parts:
        print("  " + "   ".join(parts))

    print()
    print(_sep())

    # Description
    desc = entry.get("description") or ""
    if desc:
        lines = desc.strip().splitlines()
        max_desc_lines = 15
        for line in lines[:max_desc_lines]:
            wrapped_line = textwrap.fill(line or " ", width=min(term_w - 4, 76), subsequent_indent="  ")
            print(f"  {_DIM}{wrapped_line}{_RESET}")
        if len(lines) > max_desc_lines:
            print(f"\n  {_GRAY}… ({len(lines) - max_desc_lines} more lines){_RESET}")
        print()
    else:
        print(f"  {_GRAY}(no description){_RESET}\n")

    print(_sep())
    print()


def _build_actions(entry: dict, config) -> list[str]:
    """Build action menu items, noting which files are already saved locally."""
    video_id = entry.get("id", "")
    local = library.find_local(video_id, config.video_dir, config.audio_dir)

    video_saved = "video_path" in local
    audio_saved = "audio_path" in local

    actions = []

    # Watch options
    if video_saved:
        actions.append(f"▶  Watch Video  {_GRN}[saved]{_RESET}")
    else:
        actions.append("▶  Watch Video  (stream)")

    if audio_saved:
        actions.append(f"♪  Listen to Audio  {_GRN}[saved]{_RESET}")
    else:
        actions.append("♪  Listen to Audio  (stream)")

    actions.append(_sep(30))

    # Save options
    if not video_saved:
        actions.append("⬇  Save Video")
    if not audio_saved:
        actions.append("⬇  Save Audio")

    if video_saved or audio_saved:
        actions.append("⬇  Save All (video + audio)")

    actions.append(_sep(30))
    actions.append("⭐  Subscribe to Channel")
    actions.append("🌐  Open in Browser")

    return actions


def _is_separator(item: str) -> bool:
    return item.strip().startswith("─") or item.strip().startswith("─")


def run(video_id: str, config, cache) -> None:
    """Show video detail page. Blocks until user goes back."""
    from src import ytdlp

    # Fetch full metadata (tries cache first, then yt-dlp)
    entry = gum.spin_while(
        "Loading video info…",
        lambda: ytdlp.fetch_full(video_id, config, cache),
    )

    if not entry:
        gum.error(f"Could not fetch info for {video_id}")
        input("Press Enter to go back…")
        return

    while True:
        _print_header(entry, config)

        actions = _build_actions(entry, config)
        # Filter separators from gum choose (gum doesn't handle them)
        display_actions = [a for a in actions if not _is_separator(a)]

        choice = gum.choose(
            display_actions,
            header=f"  {_BOLD}Actions{_RESET}",
            height=len(display_actions) + 2,
        )

        if choice is None:
            break  # ESC → go back

        url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
        title = entry.get("title", "")
        local = library.find_local(video_id, config.video_dir, config.audio_dir)

        if "Watch Video" in choice:
            play_url = local.get("video_path") or url
            history.add(entry)
            mpv_player.play(play_url, audio_only=False, player=config.preferred_player, title=title)

        elif "Listen to Audio" in choice:
            play_url = local.get("audio_path") or url
            history.add(entry)
            mpv_player.play(play_url, audio_only=True, player=config.preferred_player, title=title)

        elif "Save Video" in choice:
            gum.info(f"Downloading video: {title}")
            ok = gum.spin_while(
                "Downloading video…",
                lambda: ytdlp.download_video(video_id, config),
            )
            gum.success("Video saved!") if ok else gum.error("Download failed.")
            input("Press Enter to continue…")

        elif "Save Audio" in choice:
            gum.info(f"Downloading audio: {title}")
            ok = gum.spin_while(
                "Downloading audio…",
                lambda: ytdlp.download_audio(video_id, config),
            )
            gum.success("Audio saved!") if ok else gum.error("Download failed.")
            input("Press Enter to continue…")

        elif "Save All" in choice:
            gum.info(f"Downloading video + audio: {title}")
            ok_v = gum.spin_while("Downloading video…", lambda: ytdlp.download_video(video_id, config))
            ok_a = gum.spin_while("Downloading audio…", lambda: ytdlp.download_audio(video_id, config))
            if ok_v and ok_a:
                gum.success("Video and audio saved!")
            else:
                gum.error(f"Partial failure: video={'✓' if ok_v else '✗'} audio={'✓' if ok_a else '✗'}")
            input("Press Enter to continue…")

        elif "Subscribe" in choice:
            channel_url = entry.get("channel_url") or entry.get("uploader_url") or ""
            if channel_url:
                ytdlp.subscribe_channel(channel_url, config)
                gum.info("Opening channel in browser to subscribe…")
            else:
                gum.error("Channel URL not available.")
            input("Press Enter to continue…")

        elif "Open in Browser" in choice:
            ytdlp.open_in_browser(video_id)
            gum.info("Opened in browser.")
            input("Press Enter to continue…")
