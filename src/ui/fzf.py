"""fzf wrapper — streaming list UIs for all pages.

Design:
  run_list()  streams items into fzf via stdin pipe, returns selected video_id.
  Items flow in progressively — fzf populates as yt-dlp produces entries.
  The preview pane runs src/ui/preview.py {video_id} for thumbnail + metadata.
  Background enrichment fetches full metadata while fzf is open; the preview
  pane automatically shows richer data on the next cursor hover.
"""

from __future__ import annotations
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Generator

# Absolute path to the preview script — fzf calls it as a subprocess
_PREVIEW_SCRIPT = str(Path(__file__).parent / "preview.py")
_PYTHON = str(Path(sys.executable))

# ── Formatting helpers ─────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_YEL   = "\033[33m"
_GRN   = "\033[32m"
_GRAY  = "\033[90m"
_MAG   = "\033[35m"


def _fmt_views(n) -> str:
    if n is None:
        return ""
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def _fmt_duration(secs) -> str:
    if not secs:
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_date(d: str) -> str:
    """Convert yt-dlp YYYYMMDD to YYYY-MM-DD."""
    if d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or ""


def format_video_line(entry: dict) -> str:
    """
    Format one video entry as a coloured fzf display line.
    Field 1 (hidden): video_id
    Field 2+: display text
    """
    vid      = entry.get("id", "")
    title    = (entry.get("title") or "Untitled")[:72]
    channel  = (entry.get("channel") or entry.get("uploader") or "")[:30]
    date     = _fmt_date(entry.get("upload_date", ""))
    duration = _fmt_duration(entry.get("duration"))
    views    = _fmt_views(entry.get("view_count"))

    # Right-side tags
    right_parts = []
    if channel:
        right_parts.append(f"{_CYAN}{channel}{_RESET}")
    if date:
        right_parts.append(f"{_YEL}{date}{_RESET}")
    if duration:
        right_parts.append(f"{_GRN}{duration}{_RESET}")
    if views:
        right_parts.append(f"{_GRAY}{views} views{_RESET}")

    right = f"  {_GRAY}│{_RESET}  ".join(right_parts)
    display = f"  {_BOLD}{title}{_RESET}  {right}" if right else f"  {_BOLD}{title}{_RESET}"

    # Tab-separated: hidden_id \t display_text
    return f"{vid}\t{display}"


# ── Loading state indicator ────────────────────────────────────────────────────

def _wait_for_first(
    gen: Generator,
    timeout: float = 30.0,
    *,
    loading_msg: str = "Fetching...",
) -> tuple[dict | None, Generator]:
    """
    Drain the first item from gen while showing a loading animation.
    Returns (first_item, remaining_generator) or (None, empty).
    """
    q: queue.Queue = queue.Queue()
    first_event = threading.Event()
    first_item_box: list[dict | None] = [None]
    done_event = threading.Event()

    def _produce():
        try:
            for item in gen:
                if not first_event.is_set():
                    first_item_box[0] = item
                    first_event.set()
                else:
                    q.put(item)
        except Exception:
            pass
        finally:
            q.put(None)  # sentinel
            done_event.set()

    t = threading.Thread(target=_produce, daemon=True)
    t.start()

    # Animate while waiting for first item
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    deadline = time.monotonic() + timeout
    i = 0
    while not first_event.is_set() and time.monotonic() < deadline:
        sys.stderr.write(f"\r\033[K  \033[36m{frames[i % len(frames)]}\033[0m  {loading_msg}")
        sys.stderr.flush()
        time.sleep(0.08)
        i += 1

    sys.stderr.write("\r\033[K")
    sys.stderr.flush()

    first = first_item_box[0]
    if first is None:
        return None, (x for x in [])  # empty gen

    def _remaining():
        while True:
            item = q.get()
            if item is None:
                break
            yield item

    return first, _remaining()


# ── Main list runner ───────────────────────────────────────────────────────────

def run_list(
    title: str,
    entry_stream: Generator[dict, None, None],
    *,
    loading_msg: str = "Fetching...",
    preview_cols: int = 38,
    preview_rows: int = 20,
    extra_binds: list[str] | None = None,
    config=None,
    cache=None,
) -> str | None:
    """
    Show a fzf list populated progressively from entry_stream.

    Returns the selected video_id string, or None if the user pressed Esc/backspace.
    When config and cache are provided, starts background metadata enrichment so the
    preview pane progressively shows richer data as the user browses.
    """
    first, remaining = _wait_for_first(entry_stream, loading_msg=loading_msg)
    if first is None:
        print(f"\033[33m  No results found. Check your internet connection and cookie setup.\033[0m")
        return None

    preview_cmd = f"{_PYTHON} {_PREVIEW_SCRIPT} {{1}} {preview_cols} {preview_rows}"

    binds = [
        "j:down",
        "k:up",
        "h:abort",
        "l:accept",
        "backspace:abort",
        "ctrl-j:preview-down",
        "ctrl-k:preview-up",
        "ctrl-d:preview-page-down",
        "ctrl-u:preview-page-up",
    ]
    if extra_binds:
        binds.extend(extra_binds)

    fzf_cmd = [
        "fzf",
        "--ansi",
        "--header", f"  {title}  │  \033[90m↑↓/jk nav  Enter/l select  h/Esc back  / search\033[0m",
        "--with-nth=2..",
        "--delimiter=\t",
        "--preview", preview_cmd,
        "--preview-window=right:50%:wrap",
        "--bind=" + ",".join(binds),
        "--no-sort",
        "--layout=reverse",
        "--border=rounded",
        "--color=header:italic,border:240",
        "--pointer=▶",
        "--marker=✓",
        "--prompt=  🔍  ",
    ]

    fzf_proc = subprocess.Popen(
        fzf_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    seen_ids: list[str] = []
    enrichment_started = False

    def _maybe_start_enrichment(ids: list[str]) -> None:
        nonlocal enrichment_started
        if enrichment_started or not config or not cache or not ids:
            return
        enrichment_started = True
        from src import ytdlp as _ytdlp
        _ytdlp.enrich_in_background(list(ids), config, cache, max_workers=2)

    def _feed():
        try:
            # Write first item
            vid = first.get("id", "")
            if vid:
                seen_ids.append(vid)
            line = format_video_line(first)
            fzf_proc.stdin.write(line + "\n")  # type: ignore[union-attr]
            fzf_proc.stdin.flush()             # type: ignore[union-attr]

            # Stream remaining
            for entry in remaining:
                vid = entry.get("id", "")
                if vid:
                    seen_ids.append(vid)
                line = format_video_line(entry)
                fzf_proc.stdin.write(line + "\n")  # type: ignore[union-attr]
                fzf_proc.stdin.flush()             # type: ignore[union-attr]

                # Start enrichment once we have a batch of IDs
                if len(seen_ids) >= 5 and not enrichment_started:
                    _maybe_start_enrichment(seen_ids[:10])

        except (BrokenPipeError, OSError):
            pass
        finally:
            # If enrichment hasn't started yet, start it with whatever we have
            if not enrichment_started and seen_ids:
                _maybe_start_enrichment(seen_ids[:15])
            try:
                fzf_proc.stdin.close()  # type: ignore[union-attr]
            except OSError:
                pass

    feed_thread = threading.Thread(target=_feed, daemon=True)
    feed_thread.start()

    stdout, _ = fzf_proc.communicate()
    feed_thread.join(timeout=2)

    if fzf_proc.returncode != 0 or not stdout.strip():
        return None  # ESC / aborted

    selected = stdout.strip()
    video_id = selected.split("\t")[0]
    return video_id


# ── Search input ──────────────────────────────────────────────────────────────

def prompt_search(placeholder: str = "Search YouTube...") -> str | None:
    """Show a search prompt. Returns query or None."""
    import shutil as _shutil
    if _shutil.which("gum"):
        result = subprocess.run(
            ["gum", "input", "--placeholder", placeholder, "--header", "  🔍 Search YouTube"],
            stdout=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    # Fallback
    try:
        q = input("Search: ").strip()
        return q or None
    except (EOFError, KeyboardInterrupt):
        return None
