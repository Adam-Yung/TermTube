"""gum wrapper — all gum calls go through here."""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import Callable


def _has_gum() -> bool:
    return shutil.which("gum") is not None


# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    """
    Context manager that shows a spinner while a block runs.

    with Spinner("Fetching feed..."):
        do_slow_thing()
    """

    def __init__(self, title: str) -> None:
        self.title = title

    def __enter__(self) -> "Spinner":
        _print_loading(self.title)
        return self

    def __exit__(self, *_) -> None:
        _clear_loading()


def _print_loading(msg: str) -> None:
    sys.stderr.write(f"\r\033[K  \033[36m⠋\033[0m {msg}")
    sys.stderr.flush()


def _clear_loading() -> None:
    sys.stderr.write("\r\033[K")
    sys.stderr.flush()


def spin_while(title: str, fn: Callable, spinner_type: str = "dots"):
    """Run fn() while showing a spinner. Returns fn()'s return value."""
    import threading, time
    result_box: list = [None]
    exc_box: list = [None]

    def _run():
        try:
            result_box[0] = fn()
        except Exception as e:
            exc_box[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    _frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    while t.is_alive():
        sys.stderr.write(f"\r\033[K  \033[36m{_frames[i % len(_frames)]}\033[0m  {title}")
        sys.stderr.flush()
        time.sleep(0.08)
        i += 1
    _clear_loading()
    t.join()

    if exc_box[0]:
        raise exc_box[0]
    return result_box[0]


# ── Choose ────────────────────────────────────────────────────────────────────

def choose(items: list[str], *, header: str = "", height: int = 10) -> str | None:
    """Show gum choose menu. Returns selected item or None."""
    if not items:
        return None
    if not _has_gum():
        return _fallback_choose(items, header)

    cmd = ["gum", "choose", "--height", str(min(height, len(items) + 4))]
    if header:
        cmd += ["--header", header]
    cmd += items

    # Use stdout=PIPE so gum's TUI (rendered to stderr/tty) stays visible
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()
    except Exception:
        return _fallback_choose(items, header)


def _fallback_choose(items: list[str], header: str) -> str | None:
    if header:
        # Strip ANSI codes for plain display
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', header)
        print(f"\n{plain}")
    for i, item in enumerate(items, 1):
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', item)
        print(f"  {i}. {plain}")
    try:
        raw = input("\nChoice (number): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        return None
    except (EOFError, KeyboardInterrupt):
        return None


# ── Input ─────────────────────────────────────────────────────────────────────

def text_input(placeholder: str = "", header: str = "") -> str | None:
    """Show gum input. Returns entered text or None."""
    if not _has_gum():
        try:
            prompt = f"{header}\n> " if header else "> "
            return input(prompt).strip() or None
        except (EOFError, KeyboardInterrupt):
            return None

    cmd = ["gum", "input"]
    if placeholder:
        cmd += ["--placeholder", placeholder]
    if header:
        cmd += ["--header", header]

    # Use stdout=PIPE so gum's TUI renders to stderr/tty
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


# ── Confirm ───────────────────────────────────────────────────────────────────

def confirm(prompt: str, *, default: bool = True) -> bool:
    if not _has_gum():
        try:
            ans = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
            if ans == "":
                return default
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    cmd = ["gum", "confirm", prompt]
    if not default:
        cmd += ["--default=false"]
    # confirm renders TUI to stderr; exit code signals yes/no
    result = subprocess.run(cmd)
    return result.returncode == 0


# ── Style helpers ─────────────────────────────────────────────────────────────

def style(text: str, *, bold: bool = False, fg: str = "", bg: str = "", border: str = "") -> str:
    """Return ANSI-styled string using gum style, or plain fallback."""
    if not _has_gum():
        return _ansi_style(text, bold=bold, fg=fg)

    cmd = ["gum", "style"]
    if bold:
        cmd += ["--bold"]
    if fg:
        cmd += ["--foreground", fg]
    if bg:
        cmd += ["--background", bg]
    if border:
        cmd += ["--border", border]
    cmd += [text]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout.rstrip("\n")
    except Exception:
        pass
    return _ansi_style(text, bold=bold, fg=fg)


def _ansi_style(text: str, *, bold: bool = False, fg: str = "") -> str:
    codes = []
    if bold:
        codes.append("1")
    _color_map = {"red": "31", "green": "32", "yellow": "33", "blue": "34",
                  "magenta": "35", "cyan": "36", "white": "37", "gray": "90"}
    if fg in _color_map:
        codes.append(_color_map[fg])
    if codes:
        return f"\033[{';'.join(codes)}m{text}\033[0m"
    return text


def header(title: str, subtitle: str = "") -> None:
    """Print a styled page header."""
    width = 60
    print(f"\033[1;36m{title}\033[0m")
    if subtitle:
        print(f"\033[90m{subtitle}\033[0m")
    print(f"\033[90m{'─' * width}\033[0m")


def error(msg: str) -> None:
    print(f"\033[31m✗ {msg}\033[0m", file=sys.stderr)


def success(msg: str) -> None:
    print(f"\033[32m✓ {msg}\033[0m")


def info(msg: str) -> None:
    print(f"\033[36mℹ {msg}\033[0m")
