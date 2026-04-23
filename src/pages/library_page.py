"""Library page — locally saved videos and audio files."""

from __future__ import annotations
import subprocess
import threading
from src import library
from src.ui import gum
from src.ui.fzf import _wait_for_first, _PYTHON, _PREVIEW_SCRIPT

_RESET = "\033[0m"; _BOLD = "\033[1m"; _CYAN = "\033[36m"
_YEL = "\033[33m"; _GRN = "\033[32m"; _GRAY = "\033[90m"; _MAG = "\033[35m"


def _fmt_size(path_str: str | None) -> str:
    if not path_str:
        return ""
    from pathlib import Path
    try:
        size = Path(path_str).stat().st_size
        if size >= 1_073_741_824:
            return f"{size/1_073_741_824:.1f}GB"
        if size >= 1_048_576:
            return f"{size/1_048_576:.1f}MB"
        return f"{size/1_024:.0f}KB"
    except OSError:
        return ""


def _fmt_duration(secs) -> str:
    if not secs: return ""
    secs = int(secs); h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_lib_line(entry: dict) -> str:
    vid      = entry.get("id", "")
    title    = (entry.get("title") or "Untitled")[:72]
    channel  = (entry.get("channel") or entry.get("uploader") or "")[:30]
    ltype    = entry.get("_local_type", "")
    lpath    = entry.get("_local_path")
    has_aud  = entry.get("_has_audio")
    duration = _fmt_duration(entry.get("duration"))
    size     = _fmt_size(lpath)

    # Type badge
    if ltype == "video" and has_aud:
        badge = f"{_GRN}[video+audio]{_RESET}"
    elif ltype == "video":
        badge = f"{_GRN}[video]{_RESET}"
    elif ltype == "audio":
        badge = f"{_MAG}[audio]{_RESET}"
    else:
        badge = ""

    parts = []
    if channel:  parts.append(f"{_CYAN}{channel}{_RESET}")
    if badge:    parts.append(badge)
    if duration: parts.append(f"{_YEL}{duration}{_RESET}")
    if size:     parts.append(f"{_GRAY}{size}{_RESET}")

    right = f"  {_GRAY}│{_RESET}  ".join(parts)
    display = f"  {_BOLD}{title}{_RESET}  {right}"
    return f"{vid}\t{display}"


def run(config, cache) -> str | None:
    """Show local library. Returns selected video_id or None."""
    entries = library.all_entries(config.video_dir, config.audio_dir)

    if not entries:
        gum.info(
            f"Bookmarks is empty.\n"
            f"  Save videos with [Save Video] or audio with [Save Audio]\n"
            f"  from the video detail page."
        )
        input("Press Enter to go back…")
        return None

    def _stream():
        for e in entries:
            yield e

    stream = _stream()
    first, remaining = _wait_for_first(stream, loading_msg="Scanning library…")
    if first is None:
        gum.info("Library is empty.")
        return None

    fzf_cmd = [
        "fzf",
        "--ansi",
        "--header", f"  🔖  Bookmarks  ({len(entries)} items)  │  \033[90m↑↓/jk nav  Enter/l select  h/Esc back\033[0m",
        "--with-nth=2..",
        "--delimiter=\t",
        "--preview", f"{_PYTHON} {_PREVIEW_SCRIPT} {{1}} {config.thumbnail_cols} {config.thumbnail_rows}",
        "--preview-window=right:50%:wrap",
        "--bind=j:down,k:up,h:abort,l:accept,backspace:abort,ctrl-j:preview-down,ctrl-k:preview-up",
        "--no-sort",
        "--layout=reverse",
        "--border=rounded",
        "--color=header:italic,border:240",
        "--pointer=▶",
        "--prompt=  🔖  ",
    ]

    fzf_proc = subprocess.Popen(fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def _feed():
        try:
            fzf_proc.stdin.write(_format_lib_line(first) + "\n")
            fzf_proc.stdin.flush()
            for entry in remaining:
                fzf_proc.stdin.write(_format_lib_line(entry) + "\n")
                fzf_proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                fzf_proc.stdin.close()
            except OSError:
                pass

    t = threading.Thread(target=_feed, daemon=True)
    t.start()
    stdout, _ = fzf_proc.communicate()
    t.join(timeout=1)

    if fzf_proc.returncode != 0 or not stdout.strip():
        return None
    return stdout.strip().split("\t")[0]
