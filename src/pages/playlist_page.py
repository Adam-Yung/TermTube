"""Playlist page — browse, manage, and play playlists."""

from __future__ import annotations
import os
import subprocess

from src import playlist
from src.ui import gum
from src.ui.fzf import _PYTHON, _PREVIEW_SCRIPT
from src import player as mpv_player
from src import logger

_RESET = "\033[0m"; _BOLD = "\033[1m"; _CYAN = "\033[36m"
_YEL = "\033[33m"; _GRN = "\033[32m"; _GRAY = "\033[90m"; _MAG = "\033[35m"


def _fmt_duration(secs) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _show_playlist_list() -> str | None:
    """Show fzf list of playlists. Returns selected name or special token."""
    names = playlist.list_names()
    lines: list[str] = []

    for name in names:
        vids = playlist.get_playlist(name)
        count = len(vids)
        label = f"{count} video{'s' if count != 1 else ''}"
        lines.append(f"{name}\t  {_BOLD}{name}{_RESET}  {_GRAY}({label}){_RESET}")

    lines.append(f"__NEW__\t  {_GRN}➕  Create new playlist{_RESET}")

    header = (
        f"  🎵  Playlists  ({len(names)})  │  "
        f"\033[90m↑↓/jk nav  Enter/l select  h back\033[0m"
    )

    result = subprocess.run(
        [
            "fzf", "--ansi",
            "--header", header,
            "--with-nth=2..", "--delimiter=\t",
            "--no-sort", "--layout=reverse",
            "--border=rounded", "--pointer=▶",
            "--prompt=  🎵  ",
            "--bind=j:down,k:up,h:abort,l:accept,backspace:abort",
        ],
        input="\n".join(lines),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().split("\t")[0]


def _show_playlist_videos(name: str, config, cache) -> str | None:
    """
    Show fzf list of videos in a playlist.
    Returns video_id to open in detail, or None.
    Uses --expect to detect p (play-all) and ctrl-d (remove).
    """
    video_ids = playlist.get_playlist(name)

    if not video_ids:
        choice = gum.choose(
            ["➕  Add videos via Browse", "🗑  Delete this playlist", "← Back"],
            header=f"  🎵  {name}  (empty)",
        )
        if choice and "Delete" in choice:
            if gum.confirm(f"Delete playlist '{name}'?", default=False):
                playlist.delete(name)
                gum.success(f"Deleted '{name}'")
        return None

    lines = []
    for i, vid in enumerate(video_ids, 1):
        entry = cache.get_video_raw(vid) or {"id": vid}
        title = (entry.get("title") or f"[{vid}]")[:65]
        channel = (entry.get("channel") or entry.get("uploader") or "")[:28]
        dur = _fmt_duration(entry.get("duration"))
        right_parts = []
        if channel:
            right_parts.append(f"{_CYAN}{channel}{_RESET}")
        if dur:
            right_parts.append(f"{_YEL}{dur}{_RESET}")
        right = f"  {_GRAY}│{_RESET}  ".join(right_parts)
        num = f"{_GRAY}{i:>2}.{_RESET}"
        display = f"  {num} {_BOLD}{title}{_RESET}  {right}" if right else f"  {num} {_BOLD}{title}{_RESET}"
        lines.append(f"{vid}\t{display}")

    header = (
        f"  🎵  {name}  ({len(video_ids)} videos)  │  "
        f"\033[90mEnter/l select  p play-all  ctrl-d remove  h back\033[0m"
    )

    result = subprocess.run(
        [
            "fzf", "--ansi",
            "--header", header,
            "--with-nth=2..", "--delimiter=\t",
            "--no-sort", "--layout=reverse",
            "--border=rounded", "--pointer=▶",
            "--prompt=  ▶  ",
            "--preview", f"{_PYTHON} {_PREVIEW_SCRIPT} {{1}} {config.thumbnail_cols} {config.thumbnail_rows}",
            "--preview-window=right:50%:wrap:rounded",
            "--bind=j:down,k:up,h:abort,l:accept,backspace:abort,ctrl-j:preview-down,ctrl-k:preview-up",
            "--expect=p,ctrl-d",
        ],
        input="\n".join(lines),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    output = result.stdout.strip().split("\n")
    key = output[0] if output else ""
    selected_line = output[1] if len(output) > 1 else ""

    if key == "p":
        _play_all(name, video_ids, config)
        return None

    if key == "ctrl-d" and selected_line:
        vid = selected_line.split("\t")[0]
        if gum.confirm(f"Remove from '{name}'?", default=False):
            playlist.remove_video(name, vid)
            gum.success("Removed.")
        return None

    if not selected_line:
        return None
    return selected_line.split("\t")[0]


def _play_all(name: str, video_ids: list[str], config=None) -> None:
    """Play all videos in a playlist sequentially via mpv."""
    gum.info(f"Playing '{name}' ({len(video_ids)} videos)…")
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]
    ck = config.cookie_args if config else []
    try:
        mpv_player.play_playlist(urls, title=f"Playlist: {name}", cookie_args=ck)
    except Exception as exc:
        gum.error(f"Playback error: {exc}")
        logger.exception("playlist playback error")
        input("Press Enter to continue…")


def run(config, cache) -> str | None:
    """
    Playlist page entry point.
    Returns a video_id if the user wants to view it in detail, else None.
    """
    while True:
        os.system("clear")
        names = playlist.list_names()

        if not names:
            choice = gum.choose(
                ["➕  Create new playlist", "← Back"],
                header="  🎵  Playlists  (none yet)",
            )
            if not choice or "Back" in choice:
                return None
            _create_playlist()
            continue

        key = _show_playlist_list()

        if key is None:
            return None

        if key == "__NEW__":
            _create_playlist()
            continue

        # Show videos in selected playlist
        video_id = _show_playlist_videos(key, config, cache)
        if video_id:
            return video_id
        # Otherwise loop back to playlist list


def _create_playlist() -> str | None:
    """Prompt for a name and create a new empty playlist. Returns the name or None."""
    name = gum.text_input(placeholder="Playlist name…", header="  🎵  New Playlist")
    if not name:
        return None
    if name in playlist.list_names():
        gum.error(f"Playlist '{name}' already exists.")
        return None
    playlist.create(name)
    gum.success(f"Created playlist '{name}'")
    return name


def pick_playlist_for_video(video_id: str) -> None:
    """
    Show a menu to add video_id to an existing playlist or create a new one.
    Called from video_detail.py.
    """
    names = playlist.list_names()
    options = [f"  {n}" for n in names] + ["  ➕  New playlist"]

    choice = gum.choose(options, header="  🎵  Add to Playlist", height=min(len(options) + 4, 14))
    if not choice:
        return

    choice = choice.strip()
    if choice.startswith("➕"):
        name = gum.text_input(placeholder="Playlist name…", header="  🎵  New Playlist")
        if not name:
            return
        playlist.create(name)
        playlist.add_video(name, video_id)
        gum.success(f"Created '{name}' and added video.")
    else:
        added = playlist.add_video(choice, video_id)
        if added:
            gum.success(f"Added to '{choice}'")
        else:
            gum.info(f"Already in '{choice}'")
