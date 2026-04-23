"""History page — locally tracked videos watched via this TUI."""

from __future__ import annotations
import time
from src import history
from src.ui import fzf, gum


def _watched_at_str(entry: dict) -> str:
    ts = entry.get("_watched_at")
    if not ts:
        return ""
    delta = int(time.time() - ts)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _entries_as_stream(entries):
    for e in entries:
        # Inject watch time into display via upload_date slot (fake field for display)
        e = dict(e)
        watched = _watched_at_str(e)
        if watched:
            e["_display_date"] = watched
        yield e


def run(config, cache) -> str | None:
    """Show local watch history. Returns selected video_id or None."""
    entries = history.all_entries()

    if not entries:
        gum.info("No watch history yet. Watch some videos first!")
        input("Press Enter to go back…")
        return None

    def _stream():
        for e in entries:
            # Temporarily override upload_date with watched-at for display
            copy = dict(e)
            watched = _watched_at_str(copy)
            if watched:
                copy["upload_date"] = ""  # suppress original date
                copy["_watched_label"] = watched
            yield copy

    # Custom fzf format that shows "watched X ago" instead of upload date
    import queue as _queue
    import threading
    from src.ui.fzf import format_video_line, run_list
    from src.cache import Cache

    # Inject watched-at into the fzf line by monkey-patching format
    def _format_history_line(entry: dict) -> str:
        watched = entry.get("_watched_label", "")
        vid      = entry.get("id", "")
        title    = (entry.get("title") or "Untitled")[:72]
        channel  = (entry.get("channel") or entry.get("uploader") or "")[:30]
        duration_secs = entry.get("duration")

        _RESET = "\033[0m"; _BOLD = "\033[1m"; _CYAN = "\033[36m"
        _YEL = "\033[33m"; _GRN = "\033[32m"; _GRAY = "\033[90m"

        def _fmt_dur(s):
            if not s: return ""
            s = int(s); h, r = divmod(s, 3600); m, sec = divmod(r, 60)
            return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

        parts = []
        if channel:  parts.append(f"{_CYAN}{channel}{_RESET}")
        if watched:  parts.append(f"{_YEL}watched {watched}{_RESET}")
        dur = _fmt_dur(duration_secs)
        if dur:      parts.append(f"{_GRN}{dur}{_RESET}")

        right = f"  {_GRAY}│{_RESET}  ".join(parts)
        display = f"  {_BOLD}{title}{_RESET}  {right}"
        return f"{vid}\t{display}"

    import subprocess
    import sys
    from src.ui.fzf import _wait_for_first, _PYTHON, _PREVIEW_SCRIPT

    stream = _stream()
    first, remaining = _wait_for_first(stream, loading_msg="Loading history…")
    if first is None:
        gum.info("No history entries.")
        return None

    fzf_cmd = [
        "fzf",
        "--ansi",
        "--header", "  📜  Watch History  │  \033[90m↑↓/jk nav  Enter/l select  h/Esc back\033[0m",
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
        "--prompt=  🕐  ",
    ]

    fzf_proc = subprocess.Popen(fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def _feed():
        try:
            fzf_proc.stdin.write(_format_history_line(first) + "\n")
            fzf_proc.stdin.flush()
            for entry in remaining:
                fzf_proc.stdin.write(_format_history_line(entry) + "\n")
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
