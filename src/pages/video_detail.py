"""Video detail page — full info + action menu for a single video."""

from __future__ import annotations
import os
import sys
import textwrap

from src import history, library
from src.ui import gum, thumbnail as thumb
from src import player as mpv_player
from src import ytdlp
from src import logger

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_YEL   = "\033[33m"
_GRN   = "\033[32m"
_GRAY  = "\033[90m"
_MAG   = "\033[35m"
_RED   = "\033[31m"

# Sentinel used to mark separator rows so they're reliably filtered out
_SEP_SENTINEL = "__SEPARATOR__"


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
    if date and date != "—":  parts.append(f"{_YEL}📅 {date}{_RESET}")
    if duration != "—":       parts.append(f"{_GRN}⏱ {duration}{_RESET}")
    if views != "—":          parts.append(f"{_GRAY}👁 {views} views{_RESET}")
    if likes:                 parts.append(f"{_MAG}👍 {_fmt_views(likes)}{_RESET}")

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
        print(f"  {_GRAY}(loading description…){_RESET}\n")

    print(_sep())
    print()


# Actions are stored as (display_label, action_key) tuples.
# action_key None means it's a separator (skipped in menu).
_ACTIONS: list[tuple[str, str | None]] = []  # built dynamically


def _build_actions(entry: dict, config) -> list[tuple[str, str]]:
    """Build (label, key) action pairs. Separators have key=None."""
    video_id = entry.get("id", "")
    local = library.find_local(video_id, config.video_dir, config.audio_dir)

    video_saved = "video_path" in local
    audio_saved = "audio_path" in local

    actions: list[tuple[str, str | None]] = []

    if video_saved:
        actions.append((f"▶  Watch Video  {_GRN}[saved]{_RESET}", "watch"))
    else:
        actions.append(("▶  Watch Video  (stream)", "watch"))

    if audio_saved:
        actions.append((f"♪  Listen to Audio  {_GRN}[saved]{_RESET}", "listen"))
    else:
        actions.append(("♪  Listen to Audio  (stream)", "listen"))

    actions.append((_SEP_SENTINEL, None))

    if not video_saved:
        actions.append(("⬇  Save Video", "save_video"))
    if not audio_saved:
        actions.append(("⬇  Save Audio", "save_audio"))
    if video_saved or audio_saved:
        actions.append(("⬇  Save All (video + audio)", "save_all"))

    actions.append((_SEP_SENTINEL, None))
    actions.append(("⭐  Subscribe to Channel", "subscribe"))
    actions.append(("🌐  Open in Browser", "browser"))
    actions.append(("← Back", "back"))

    return actions


def run(video_id: str, config, cache) -> None:
    """Show video detail page. Blocks until user goes back."""
    logger.debug("video_detail.run: %s", video_id)

    # Try flat cache first for instant display, then fetch full in background
    flat = cache.get_video_raw(video_id)

    # Fetch full metadata (tries cache first, then yt-dlp)
    entry = gum.spin_while(
        "Loading video info…",
        lambda: ytdlp.fetch_full(video_id, config, cache),
    )

    if not entry:
        # Fall back to flat data we may have
        entry = flat
    if not entry:
        gum.error(f"Could not fetch info for video: {video_id}")
        input("Press Enter to go back…")
        return

    while True:
        _print_header(entry, config)

        all_actions = _build_actions(entry, config)
        # Filter out separators for the gum choose list
        display = [(label, key) for label, key in all_actions if key is not None]
        labels = [label for label, _ in display]
        key_map = {label: key for label, key in display}

        choice_label = gum.choose(
            labels,
            header=f"  {_BOLD}Actions{_RESET}",
            height=len(labels) + 3,
        )

        if choice_label is None:
            break  # ESC / back

        action_key = key_map.get(choice_label)
        if action_key is None or action_key == "back":
            break

        url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
        title = entry.get("title", "")
        local = library.find_local(video_id, config.video_dir, config.audio_dir)

        if action_key == "watch":
            play_url = local.get("video_path") or url
            history.add(entry)
            try:
                mpv_player.play(play_url, audio_only=False, player=config.preferred_player, title=title)
            except Exception as exc:
                gum.error(f"Playback error: {exc}")
                logger.exception("mpv playback error")
                input("Press Enter to continue…")

        elif action_key == "listen":
            play_url = local.get("audio_path") or url
            history.add(entry)
            try:
                mpv_player.play(play_url, audio_only=True, player=config.preferred_player, title=title)
            except Exception as exc:
                gum.error(f"Playback error: {exc}")
                logger.exception("mpv playback error")
                input("Press Enter to continue…")

        elif action_key == "save_video":
            gum.info(f"Downloading video: {title}")
            ok = gum.spin_while(
                "Downloading video…",
                lambda: ytdlp.download_video(video_id, config),
            )
            gum.success("Video saved!") if ok else gum.error("Download failed.")
            input("Press Enter to continue…")

        elif action_key == "save_audio":
            gum.info(f"Downloading audio: {title}")
            ok = gum.spin_while(
                "Downloading audio…",
                lambda: ytdlp.download_audio(video_id, config),
            )
            gum.success("Audio saved!") if ok else gum.error("Download failed.")
            input("Press Enter to continue…")

        elif action_key == "save_all":
            gum.info(f"Downloading video + audio: {title}")
            ok_v = gum.spin_while("Downloading video…", lambda: ytdlp.download_video(video_id, config))
            ok_a = gum.spin_while("Downloading audio…", lambda: ytdlp.download_audio(video_id, config))
            if ok_v and ok_a:
                gum.success("Video and audio saved!")
            else:
                gum.error(f"Partial: video={'✓' if ok_v else '✗'} audio={'✓' if ok_a else '✗'}")
            input("Press Enter to continue…")

        elif action_key == "subscribe":
            channel_url = entry.get("channel_url") or entry.get("uploader_url") or ""
            if channel_url:
                ytdlp.subscribe_channel(channel_url, config)
                gum.info("Opening channel page in browser to subscribe…")
            else:
                gum.error("Channel URL not available for this video.")
            input("Press Enter to continue…")

        elif action_key == "browser":
            ytdlp.open_in_browser(video_id)
            gum.info("Opened in browser.")
            input("Press Enter to continue…")
