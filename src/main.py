#!/usr/bin/env python3
"""TermTube entry point."""

from __future__ import annotations

import argparse
import atexit
import contextlib
import datetime
import importlib
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# ``python src/main.py`` puts src/ on the path, not the project root the imports below need.
sys.path.insert(0, str(Path(__file__).parent.parent))


# Managed tools win over system copies.
from src.plat import ProcessRegistry, get_deps_bin
from src.strings import text as ui

_deps_bin = get_deps_bin()
if _deps_bin.is_dir():
    os.environ["PATH"] = str(_deps_bin) + os.pathsep + os.environ.get("PATH", "")

_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()


def _supports_color() -> bool:
    """Honors NO_COLOR and TERM=dumb."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str, *, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def _untrusted_dir_message(exc: PermissionError) -> str:
    where = exc.filename or ui("main.temp_dir")
    return ui("main.untrusted_dir", where=where, reason=exc.strerror or ui("main.untrusted_reason"))


_BANNER_WIDTH = 39


def _banner_row(text: str, *, color: bool) -> str:
    pad = (_BANNER_WIDTH - len(text)) // 2
    right = _BANNER_WIDTH - len(text) - pad
    return "  " + _c("1", "\u2502" + " " * pad + text + " " * right + "\u2502", color=color)


def _print_banner(color: bool) -> None:
    line = "\u2500" * _BANNER_WIDTH
    print()
    print("  " + _c("1", "\u250c" + line + "\u2510", color=color))
    print(_banner_row(f"TermTube  {_VERSION}", color=color))
    print(_banner_row(ui("main.tagline"), color=color))
    print("  " + _c("1", "\u2514" + line + "\u2518", color=color))
    print()


def _print_option(flags: str, meta: str, desc: str, *, color: bool) -> None:
    meta_str = _c("33", meta, color=color) if meta else ""
    lhs = f"  {_c('36', flags, color=color)}" + (f" {meta_str}" if meta_str else "")
    lhs_plain = f"  {flags}" + (f" {meta}" if meta else "")
    print(lhs + " " * max(1, 34 - len(lhs_plain)) + desc)


_HELP_OPTIONS = (
    ("--config", "FILE", "main.opt_config"),
    ("--browser-help", "", "main.opt_browser_help"),
    ("--clear-cache", "", "main.opt_clear_cache"),
    ("--clear-history", "", "main.opt_clear_history"),
    ("--debug", "", "main.opt_debug"),
    ("--level", "LEVEL", "main.opt_level"),
    ("--update", "", "main.opt_update"),
    ("--version", "", "main.opt_version"),
    ("--test", "", "main.opt_test"),
    ("-h, --help", "", "main.opt_help"),
)


def _config_path_shown() -> str:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", r"%APPDATA%")
        return rf"{appdata}\TermTube\config.yaml"
    return str(Path.home() / ".config" / "TermTube" / "config.yaml")


def _print_help() -> None:
    color = _supports_color()
    _print_banner(color)

    prog = _c("1;32", "termtube", color=color)
    opts = _c("36", "[OPTIONS]", color=color)
    print(f"  {_c('1', ui('main.usage'), color=color)}  {prog} {opts}")
    print()

    print("  " + _c("1", ui("main.options"), color=color))
    for flags, meta, key in _HELP_OPTIONS:
        _print_option(flags, meta, ui(key), color=color)
    print()

    print("  " + _c("1", ui("main.paths"), color=color))
    print(f"    {_c('2', ui('main.config_label'), color=color)}  {_c('36', _config_path_shown(), color=color)}")
    print()

    print("  " + _c("2", ui("main.browser_setup"), color=color)
          + "  " + _c("36", "termtube --browser-help", color=color))
    print()


def _run_tests() -> None:
    """Run pytest, echoing to the terminal and saving a copy in the temp dir."""
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "src" / "tests"

    if not tests_dir.exists():
        print("\033[31m" + ui("main.tests_missing") + "\033[0m")
        print(ui("main.tests_expected", path=tests_dir))
        sys.exit(1)

    tmp_base = Path(tempfile.gettempdir()) / "TermTube"
    tmp_base.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = tmp_base / f"test_results_{timestamp}.log"

    print(f"\033[1m{'=' * 60}\033[0m")
    print("\033[1m  " + ui("main.test_suite") + "\033[0m")
    print(f"\033[1m{'=' * 60}\033[0m")
    print(ui("main.log_file", path=f"\033[36m{log_path}\033[0m"))
    print()

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
        print("\033[31m" + ui("main.pytest_missing") + "\033[0m")
        sys.exit(1)

    lines: list[str] = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    proc.wait()

    _write_test_log(log_path, cmd, proc.returncode, lines)
    _print_test_summary(log_path, proc.returncode)
    sys.exit(proc.returncode)


def _write_test_log(log_path: Path, cmd: list[str], returncode: int, lines: list[str]) -> None:
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"TermTube Test Results — {datetime.datetime.now().isoformat()}\n")
        f.write(f"Command: {' '.join(cmd)}\n")
        f.write(f"Exit code: {returncode}\n")
        f.write("=" * 60 + "\n\n")
        f.writelines(lines)


def _print_test_summary(log_path: Path, returncode: int) -> None:
    print()
    print(f"\033[1m{'=' * 60}\033[0m")
    if returncode == 0:
        print("  \033[32m" + ui("main.tests_passed") + "\033[0m")
    else:
        print("  \033[31m" + ui("main.tests_failed", code=returncode) + "\033[0m")
    print(ui("main.results_saved", path=f"\033[36m{log_path}\033[0m"))
    print(f"\033[1m{'=' * 60}\033[0m")


def _migrate_legacy_windows_paths() -> None:
    r"""Move history/playlists from the old ~/.config/TermTube to %APPDATA%\TermTube (Windows only)."""
    if sys.platform != "win32":
        return
    from src.plat import get_config_dir
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="termtube",
        description=ui("main.description"),
        add_help=False,
    )
    parser.add_argument("--config", metavar="FILE", help=ui("main.opt_config"))
    parser.add_argument("--browser-help", action="store_true", help=ui("main.opt_browser_help"))
    parser.add_argument("--clear-cache", action="store_true", help=ui("main.opt_clear_cache"))
    parser.add_argument("--clear-history", action="store_true", help=ui("main.opt_clear_history"))
    parser.add_argument(
        "--debug",
        action="store_true",
        help=ui("main.arg_debug"),
    )
    parser.add_argument(
        "--level",
        metavar="LEVEL",
        default="ALL",
        choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=ui("main.arg_level"),
    )
    parser.add_argument("--version", action="store_true", help=ui("main.opt_version"))
    parser.add_argument("--update", action="store_true", help=ui("main.opt_update"))
    parser.add_argument("--test", action="store_true", help=ui("main.arg_test"))
    parser.add_argument("-h", "--help", action="store_true", help=ui("main.opt_help"))
    return parser


def _run_command(args: argparse.Namespace) -> int | None:
    """Run the one-shot command ``args`` asks for and return its exit code; None means start the app."""
    if args.version:
        print(f"TermTube {_VERSION}")
        return 0

    if args.browser_help:
        from src.deps import print_cookies_help
        print_cookies_help()
        return 0

    if args.clear_history:
        from src import history, search_history
        history.clear()
        search_history.clear()
        print(ui("main.history_cleared"))
        return 0

    if args.update:
        from src.updater import self_update
        color = _supports_color()
        print(_c("1", ui("main.updating"), color=color))
        return 0 if self_update() else 1
    return None


def _load_config(args: argparse.Namespace):
    """Check the required tools and read the config; exits 1 when a tool is missing."""
    from src import logger
    from src.deps import check_dependencies
    logger.debug("Running dependency check")
    if not check_dependencies():
        logger.error("Dependency check failed; exiting")
        sys.exit(1)

    from src.config import Config
    config = Config(args.config)
    logger.stage("config loaded")
    logger.debug("Config loaded from %s", getattr(config, "path", args.config or "default"))
    return config


def _clear_cache() -> None:
    from src import logger
    from src.cache import Cache
    cache = Cache({})
    logger.info("Clearing all cache")
    cache.clear_all()
    print(ui("main.cache_cleared"))


def _create_app(config):
    # Must precede Textual: textual_image probes the terminal at import, which fails once Textual's I/O threads run.
    with contextlib.suppress(ImportError):
        importlib.import_module("textual_image.widget")

    try:
        from src.tui.app import TermTubeApp
        return TermTubeApp(config)
    except PermissionError as exc:  # player.py resolves the IPC directory at import and refuses an untrusted one
        print(_untrusted_dir_message(exc), file=sys.stderr)
        sys.exit(1)


def _emergency_cleanup() -> None:
    """Kill children, close mpv sockets and cancel yt-dlp work; each step runs even if another fails."""
    try:
        ProcessRegistry.get().kill_all(timeout=1.5)
    except Exception:
        pass
    try:
        from src.player import close_all_sockets
        close_all_sockets()
    except Exception:
        pass
    try:
        ytdlp = sys.modules.get("src.ytdlp")  # never imported means nothing to cancel; importing it costs 170 ms
        if ytdlp:
            ytdlp.cancel_all()
    except Exception:
        pass


def _signal_handler(signum: int, frame) -> None:
    _emergency_cleanup()
    sys.exit(128 + signum)


def _install_exit_handlers() -> None:
    atexit.register(_emergency_cleanup)

    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGHUP, _signal_handler)


def main() -> None:
    from src import local_files

    local_files.capture_launch_dir()  # first: the Local tab opens where the user started TermTube
    args = _parser().parse_args()

    if args.help:
        _print_help()
        sys.exit(0)

    if args.test:
        _run_tests()
        sys.exit(0)

    from src import logger
    logger.setup(debug=args.debug, level=args.level)
    logger.info("TermTube starting (debug=%s, level=%s)", args.debug, args.level)

    _migrate_legacy_windows_paths()

    code = _run_command(args)
    if code is not None:
        sys.exit(code)

    config = _load_config(args)
    if args.clear_cache:
        _clear_cache()
        sys.exit(0)

    app = _create_app(config)
    _install_exit_handlers()

    try:
        app.run()
    except KeyboardInterrupt:
        pass

    if args.debug:
        log_path = logger.log_file()
        if log_path:
            print(ui("main.logs_saved", path=log_path))


if __name__ == "__main__":
    main()
