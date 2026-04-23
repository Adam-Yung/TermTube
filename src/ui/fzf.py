"""fzf wrapper — streaming list UIs for all pages.

Design:
  run_list()  streams items into fzf via stdin pipe, returns selected video_id.
  Items flow progressively — fzf populates as yt-dlp produces entries.

  Performance features:
    - Background thumbnail preloading for the first 15 entries
    - Background metadata enrichment (fills cache for preview)
    - Cache-first streaming in ytdlp.stream_flat / stream_search

  UI features (fzf 0.70):
    - --border-label  for page title panel header
    - --preview-label for the preview panel title
    - --scrollbar     for visible scroll indicator
    - --padding       for inner breathing room
    - kitty graphics protocol (if KITTY_WINDOW_ID is set)
"""

from __future__ import annotations
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Generator

# Absolute path to the preview script — fzf calls it as a subprocess
_PREVIEW_SCRIPT = str(Path(__file__).parent / "preview.py")
_PYTHON = str(Path(sys.executable))

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_CYAN  = "\033[36m"
_YEL   = "\033[33m"
_GRN   = "\033[32m"
_GRAY  = "\033[90m"
_MAG   = "\033[35m"


# ── Item formatting ───────────────────────────────────────────────────────────

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
        return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_date(d: str) -> str:
    if d and len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or ""


def format_video_line(entry: dict) -> str:
    """
    Format one video entry as a coloured fzf display line.
    Tab-separated: hidden_id \\t display_text
    fzf uses --with-nth=2.. to hide the id column.
    """
    vid      = entry.get("id", "")
    title    = (entry.get("title") or "Untitled")[:72]
    channel  = (entry.get("channel") or entry.get("uploader") or "")[:28]
    date     = _fmt_date(entry.get("upload_date", ""))
    duration = _fmt_duration(entry.get("duration"))
    views    = _fmt_views(entry.get("view_count"))

    right_parts = []
    if channel:
        right_parts.append(f"{_CYAN}{channel}{_RESET}")
    if date:
        right_parts.append(f"{_YEL}{date}{_RESET}")
    if duration:
        right_parts.append(f"{_GRN}{duration}{_RESET}")
    if views:
        right_parts.append(f"{_GRAY}{views}{_RESET}")

    right = f"  {_GRAY}·{_RESET}  ".join(right_parts)
    display = f"  {_BOLD}{title}{_RESET}  {right}" if right else f"  {_BOLD}{title}{_RESET}"
    return f"{vid}\t{display}"


# ── Loading state indicator ────────────────────────────────────────────────────

def _wait_for_first(
    gen: Generator,
    timeout: float = 30.0,
    *,
    loading_msg: str = "Fetching...",
) -> tuple[dict | None, Generator]:
    """
    Drain the first item from gen while showing a spinner.
    Returns (first_item, remaining_generator) or (None, empty).
    """
    q: queue.Queue = queue.Queue()
    first_event = threading.Event()
    first_item_box: list[dict | None] = [None]

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

    t = threading.Thread(target=_produce, daemon=True)
    t.start()

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
        return None, (x for x in [])

    def _remaining():
        while True:
            item = q.get()
            if item is None:
                break
            yield item

    return first, _remaining()


# ── fzf command builder ───────────────────────────────────────────────────────

def _build_fzf_cmd(
    title: str,
    preview_cols: int,
    preview_rows: int,
    extra_binds: list[str] | None,
) -> list[str]:
    """Build the fzf command with all styling flags."""
    # Use fzf's live pane-size env vars so chafa renders at the actual preview width/height.
    # $FZF_PREVIEW_COLUMNS and $FZF_PREVIEW_LINES are set by fzf before each preview run.
    preview_cmd = f"{_PYTHON} {_PREVIEW_SCRIPT} {{1}} $FZF_PREVIEW_COLUMNS $FZF_PREVIEW_LINES"

    # Navigation hint shown inside the border (compact)
    nav_hint = (
        f"\033[90m"
        f"↑↓ / jk  navigate   "
        f"Enter / l  select   "
        f"h  back   "
        f"/  search   "
        f"C-j/k  scroll preview"
        f"\033[0m"
    )

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
        "ctrl-f:preview-page-down",
        "ctrl-b:preview-page-up",
    ]
    if extra_binds:
        binds.extend(extra_binds)

    # Border label with page title (clean, no emoji duplication in label)
    border_label = f"  {title}  "

    cmd = [
        "fzf",
        "--ansi",
        # Panel borders
        "--border=rounded",
        f"--border-label={border_label}",
        "--border-label-pos=3",   # position from left
        # Preview panel
        "--preview", preview_cmd,
        "--preview-window=right:55%:wrap:rounded",
        "--preview-label=  📺 Preview  ",
        # List styling
        "--with-nth=2..",
        "--delimiter=\t",
        "--no-sort",
        "--layout=reverse",
        "--padding=0,1",          # 1-char inner horizontal padding
        "--scrollbar=▐",
        "--pointer=▶",
        "--marker=✓",
        "--prompt=  🔍  ",
        "--info=right",           # show match count on the right
        # Colors (subtle, works with dark and light themes)
        "--color=border:bright-black,label:bright-cyan:bold,"
                "preview-border:bright-black,preview-label:bright-cyan,"
                "pointer:cyan,marker:green,prompt:cyan,"
                "header:italic,info:bright-black",
        # Key bindings
        "--bind=" + ",".join(binds),
        # Header (navigation help, shown at the bottom of the list in reverse layout)
        "--header", nav_hint,
    ]
    return cmd


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
    Show a progressively-loaded fzf list from entry_stream.

    Returns the selected video_id, or None if the user pressed Esc / h / backspace.

    When config + cache are provided:
      - Starts background metadata enrichment (fills preview cache)
      - Starts background thumbnail preloading for the first 15 entries
    """
    first, remaining = _wait_for_first(entry_stream, loading_msg=loading_msg)
    if first is None:
        print(f"\033[33m  No results found. Check your connection and cookie setup.\033[0m")
        input("  Press Enter to go back…")
        return None

    fzf_cmd = _build_fzf_cmd(title, preview_cols, preview_rows, extra_binds)

    fzf_proc = subprocess.Popen(
        fzf_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    # State for background jobs
    seen_ids: list[str] = []
    thumb_pairs: list[tuple[str, str]] = []   # (video_id, thumbnail_url)
    enrichment_started = False
    thumb_preload_started = False

    def _maybe_start_enrichment():
        nonlocal enrichment_started
        if enrichment_started or not config or not cache:
            return
        enrichment_started = True
        from src import ytdlp as _ytdlp
        _ytdlp.enrich_in_background(list(seen_ids[:15]), config, cache, max_workers=2)

    def _maybe_start_thumb_preload():
        nonlocal thumb_preload_started
        if thumb_preload_started or not thumb_pairs:
            return
        thumb_preload_started = True
        from src.ui.thumbnail import download_background
        download_background(list(thumb_pairs[:15]))

    def _collect(entry: dict) -> None:
        """Track IDs and thumbnail URLs from each entry as it arrives."""
        vid = entry.get("id", "")
        url = entry.get("thumbnail", "")
        if vid:
            seen_ids.append(vid)
        if vid and url:
            thumb_pairs.append((vid, url))

    def _feed():
        try:
            # First item
            _collect(first)
            fzf_proc.stdin.write(format_video_line(first) + "\n")  # type: ignore[union-attr]
            fzf_proc.stdin.flush()                                  # type: ignore[union-attr]

            # Stream remaining items
            for entry in remaining:
                _collect(entry)
                fzf_proc.stdin.write(format_video_line(entry) + "\n")  # type: ignore[union-attr]
                fzf_proc.stdin.flush()                                  # type: ignore[union-attr]

                # Start thumbnail preload once we have 5 entries
                if len(thumb_pairs) >= 5 and not thumb_preload_started:
                    _maybe_start_thumb_preload()

                # Start metadata enrichment once we have 10 entries
                if len(seen_ids) >= 10 and not enrichment_started:
                    _maybe_start_enrichment()

        except (BrokenPipeError, OSError):
            pass
        finally:
            # Start any background jobs that haven't started yet
            if not thumb_preload_started:
                _maybe_start_thumb_preload()
            if not enrichment_started:
                _maybe_start_enrichment()
            try:
                fzf_proc.stdin.close()  # type: ignore[union-attr]
            except OSError:
                pass

    feed_thread = threading.Thread(target=_feed, daemon=True)
    feed_thread.start()

    stdout, _ = fzf_proc.communicate()
    feed_thread.join(timeout=2)

    if fzf_proc.returncode != 0 or not stdout.strip():
        return None

    selected = stdout.strip()
    video_id = selected.split("\t")[0]
    return video_id


# ── Search input ──────────────────────────────────────────────────────────────

def prompt_search(placeholder: str = "Search YouTube...") -> str | None:
    """Show a search prompt using gum input. Returns query or None."""
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
    try:
        q = input("Search: ").strip()
        return q or None
    except (EOFError, KeyboardInterrupt):
        return None
