#!/usr/bin/env python3
"""TermTube entry point."""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_VERSION = "0.2.0"


# ── Colour helpers ─────────────────────────────────────────────────────────────

def _supports_color() -> bool:
    """True if the terminal likely supports ANSI colour codes."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str, *, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def _print_help() -> None:
    """Print a styled, colourful help screen."""
    color = _supports_color()

    # ── Banner ────────────────────────────────────────────────────────────────
    width   = 41
    inner   = width - 2
    line    = "\u2500" * inner          # ─
    tl, tr  = "\u250c", "\u2510"        # ┌ ┐
    bl, br  = "\u2514", "\u2518"        # └ ┘
    vbar    = "\u2502"                  # │

    def _banner_row(text: str) -> str:
        pad   = (inner - len(text)) // 2
        right = inner - len(text) - pad
        row   = vbar + " " * pad + text + " " * right + vbar
        return "  " + (_c("1", row, color=color) if color else row)

    print()
    print("  " + _c("1", tl + line + tr, color=color))
    print(_banner_row(f"TermTube  v{_VERSION}"))
    print(_banner_row("YouTube TUI \u2014 yt-dlp + Textual"))
    print("  " + _c("1", bl + line + br, color=color))
    print()

    # ── Usage ─────────────────────────────────────────────────────────────────
    prog = _c("1;32", "termtube", color=color)
    opts = _c("36", "[OPTIONS]", color=color)
    print(f"  {_c('1', 'Usage:', color=color)}  {prog} {opts}")
    print()

    # ── Options ───────────────────────────────────────────────────────────────
    def _opt(flags: str, meta: str, desc: str) -> None:
        flag_str = _c("36", flags, color=color)
        meta_str = _c("33", meta,  color=color) if meta else ""
        lhs = f"  {flag_str}" + (f" {meta_str}" if meta_str else "")
        # pad to column 32
        lhs_plain = f"  {flags}" + (f" {meta}" if meta else "")
        pad = max(1, 34 - len(lhs_plain))
        print(lhs + " " * pad + desc)

    print("  " + _c("1", "Options:", color=color))
    _opt("--config",        "FILE",  "Path to config YAML")
    _opt("--cookies-help",  "",      "Show cookies.txt setup instructions")
    _opt("--clear-cache",   "",      "Clear all cached feeds and metadata")
    _opt("--debug",         "",      "Enable in-app debug log (Ctrl+D) + log file")
    _opt("--level",         "LEVEL", "Log severity: ALL|DEBUG|INFO|WARNING|ERROR|CRITICAL")
    _opt("--update",        "",      "Update yt-dlp, Deno, mpv, ffmpeg to latest, then exit")
    _opt("--version",       "",      "Show version and exit")
    _opt("--test",          "",      "Run the full test suite")
    _opt("-h, --help",      "",      "Show this message and exit")
    print()

    # ── Paths ─────────────────────────────────────────────────────────────────
    print("  " + _c("1", "Paths:", color=color))
    if sys.platform == "win32":
        appdata  = os.environ.get("APPDATA",    r"%APPDATA%")
        cfg_path = rf"{appdata}\TermTube\config.yaml"
        ck_path  = rf"{appdata}\TermTube\cookies.txt"
    else:
        home     = Path.home()
        cfg_path = str(home / ".config" / "TermTube" / "config.yaml")
        ck_path  = str(home / ".config" / "TermTube" / "cookies.txt")

    print(f"    {_c('2', 'Config: ', color=color)}  {_c('36', cfg_path, color=color)}")
    print(f"    {_c('2', 'Cookies:', color=color)}  {_c('36', ck_path,  color=color)}")
    print()

    # ── Docs hint ─────────────────────────────────────────────────────────────
    print("  " + _c("2", "For cookie setup:", color=color)
          + "  " + _c("36", "termtube --cookies-help", color=color))
    print()


def _run_tests() -> None:
    """Run the full test suite, printing results to terminal and saving to a log file."""
    import subprocess
    import tempfile
    import datetime

    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "tests"

    if not tests_dir.exists():
        print("\033[31mError: tests/ directory not found.\033[0m")
        print(f"Expected at: {tests_dir}")
        sys.exit(1)

    # Determine log file location
    tmp_base = Path(tempfile.gettempdir()) / "TermTube"
    tmp_base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = tmp_base / f"test_results_{timestamp}.log"

    print(f"\033[1m{'=' * 60}\033[0m")
    print(f"\033[1m  TermTube Test Suite\033[0m")
    print(f"\033[1m{'=' * 60}\033[0m")
    print(f"  Log file: \033[36m{log_path}\033[0m")
    print()

    # Run pytest with output to both terminal and file
    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-v", "--tb=short",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(project_root),
        )
    except FileNotFoundError:
        print("\033[31mError: pytest not found. Install with: pip install pytest pytest-asyncio\033[0m")
        sys.exit(1)

    lines: list[str] = []
    for line in proc.stdout:  # type: ignore[union-attr]
        print(line, end="")
        lines.append(line)
    proc.wait()

    # Write to log file
    with open(log_path, "w") as f:
        f.write(f"TermTube Test Results — {datetime.datetime.now().isoformat()}\n")
        f.write(f"Command: {' '.join(cmd)}\n")
        f.write(f"Exit code: {proc.returncode}\n")
        f.write("=" * 60 + "\n\n")
        f.writelines(lines)

    print()
    print(f"\033[1m{'=' * 60}\033[0m")
    if proc.returncode == 0:
        print(f"  \033[32mAll tests passed.\033[0m")
    else:
        print(f"  \033[31mSome tests failed (exit code {proc.returncode}).\033[0m")
    print(f"  Results saved to: \033[36m{log_path}\033[0m")
    print(f"\033[1m{'=' * 60}\033[0m")

    sys.exit(proc.returncode)



def _migrate_legacy_windows_paths() -> None:
    """One-time migration for Windows users whose data landed at the wrong path.

    Older builds hardcoded Path.home() / ".config" / "TermTube" instead of
    using get_config_dir() which resolves to %APPDATA%\TermTube on Windows.
    Move any files found at the legacy location to the correct one.
    """
    import os
    if os.sys.platform != "win32":
        return
    from pathlib import Path
    from src.platform import get_config_dir
    correct = get_config_dir()
    legacy  = Path.home() / ".config" / "TermTube"
    if not legacy.exists():
        return
    for name in ("history.json", "playlists.json"):
        old = legacy / name
        new = correct / name
        if old.exists() and not new.exists():
            try:
                new.parent.mkdir(parents=True, exist_ok=True)
                old.rename(new)
            except OSError:
                pass

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="termtube",
        description="TermTube — YouTube TUI powered by yt-dlp + Textual",
        add_help=False,
    )
    parser.add_argument("--config", metavar="FILE", help="Path to config YAML")
    parser.add_argument("--cookies-help", action="store_true", help="Show cookies.txt setup instructions")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached feeds and metadata")
    parser.add_argument("--debug", action="store_true", help="Enable logging to the in-app debug window (Ctrl+D) and $TMPDIR/TermTube/<timestamp>.log. Nothing is written to stderr.")
    parser.add_argument(
        "--level",
        metavar="LEVEL",
        default="ALL",
        choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum log severity to keep when --debug is set. One of ALL|DEBUG|INFO|WARNING|ERROR|CRITICAL. Default: ALL (everything).",
    )
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--update", action="store_true", help="Update yt-dlp, Deno, mpv, and ffmpeg to latest versions, then exit")
    parser.add_argument("--test", action="store_true", help="Run the full test suite and save results to a log file")
    parser.add_argument("-h", "--help", action="store_true", help="Show this message and exit")
    args = parser.parse_args()

    if args.help:
        _print_help()
        sys.exit(0)

    # Handle --test before any other setup
    if args.test:
        _run_tests()
        sys.exit(0)

    # Set up logging before anything else
    from src import logger
    logger.setup(debug=args.debug, level=args.level)
    logger.info("TermTube starting (debug=%s, level=%s)", args.debug, args.level)

    _migrate_legacy_windows_paths()

    if args.version:
        print(f"TermTube {_VERSION}")
        sys.exit(0)

    if args.cookies_help:
        from src.deps import print_cookies_help
        print_cookies_help()
        sys.exit(0)

    # --update: run all tool updates synchronously, then exit (no TUI)
    if args.update:
        from src.updater import run_all_updates
        color = _supports_color()
        print(_c("1", "TermTube — updating tools…", color=color))
        success = run_all_updates(verbose=True)
        if success:
            print(_c("1;32", "All updates complete.", color=color))
        else:
            print(_c("1;33", "Some updates failed (see above).", color=color))
        sys.exit(0 if success else 1)

    # Dependency check
    from src.deps import check_dependencies
    logger.debug("Running dependency check")
    if not check_dependencies():
        logger.error("Dependency check failed; exiting")
        sys.exit(1)

    # Load config
    from src.config import Config
    config = Config(args.config)
    logger.debug("Config loaded from %s", getattr(config, "path", args.config or "default"))

    if args.clear_cache:
        from src.cache import Cache
        cache = Cache({})
        logger.info("Clearing all cache")
        cache.clear_all()
        print("Cache cleared.")
        sys.exit(0)

    # Warn if no cookie source is configured
    if not config.cookie_args:
        print("\033[33m⚠ No cookie source configured. Home feed and subscriptions require authentication.\033[0m")
        print("  Run: termtube --cookies-help  for setup instructions.\n")

    # Import textual_image.widget BEFORE launching Textual — the library queries the
    # terminal for sixel/TGP support and cell dimensions at import time, and those
    # queries stop working once Textual's I/O threads are running.
    try:
        import textual_image.widget  # noqa: F401 — side-effect import for detection
    except ImportError:
        pass

    # Launch Textual TUI
    from src.tui.app import TermTubeApp
    app = TermTubeApp(config)

    # Ensure mpv and yt-dlp subprocesses are cleaned up on any exit (crash, Ctrl+C, etc.)
    import atexit
    from src import ytdlp as _ytdlp

    def _emergency_cleanup() -> None:
        try:
            _ytdlp.kill_all_active()
        except Exception:
            pass
        try:
            screen = app.screen
            if hasattr(screen, "_audio_proc") and screen._audio_proc is not None:
                from src.platform import terminate_process
                terminate_process(screen._audio_proc, timeout=1.0)
        except Exception:
            pass

    atexit.register(_emergency_cleanup)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            from src.updater import maybe_update
            maybe_update()
        except Exception:
            pass


if __name__ == "__main__":
    main()
