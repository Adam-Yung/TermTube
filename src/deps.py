"""Startup check for the required external tools; offers to install missing ones."""

from __future__ import annotations

import sys

from src.plat import get_config_dir, get_deps_bin, is_tool_installed
from src.strings import text

REQUIRED_TOOLS: list[str] = ["deno", "mpv", "ffmpeg"]


def print_cookies_help() -> None:
    conf = str(get_config_dir() / "config.yaml")
    print()
    print("\033[1;36m" + text("deps.cookies_title") + "\033[0m")
    print()
    print(text("deps.cookies_body", config=f"\033[36m{conf}\033[0m"))
    print()


def check_dependencies() -> bool:
    """True if all required tools exist in the managed bin dir; system copies never count.

    If any are missing and stdin is a TTY, offers to install them via src.bootstrap.
    """
    missing = [tool for tool in REQUIRED_TOOLS if not is_tool_installed(tool)]
    if not missing:
        return True

    print("\n\033[31m" + text("deps.missing", path=get_deps_bin()) + "\033[0m")
    for tool in missing:
        print(f"  • {tool}")

    if not sys.stdin.isatty():
        _print_bootstrap_hint()
        return False

    return _offer_bootstrap(missing)


def _offer_bootstrap(missing: list[str]) -> bool:
    from src.bootstrap import install_tool

    print()
    print(text("deps.offer", path=f"\033[36m{get_deps_bin()}\033[0m"))
    print()

    try:
        ans = input(text("deps.prompt")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans not in ("", "y", "yes"):
        _print_bootstrap_hint()
        return False

    all_ok = True
    for tool in missing:
        print(text("deps.installing", tool=tool), flush=True)
        if install_tool(tool, force=True):
            print("\033[32m" + text("deps.installed", tool=tool) + "\033[0m")
        else:
            print("\033[31m" + text("deps.failed", tool=tool) + "\033[0m")
            all_ok = False

    if all_ok:
        print()
    return all_ok


def _print_bootstrap_hint() -> None:
    print("\n" + text("deps.manual", command="\033[36mpython -m src.bootstrap\033[0m", path=get_deps_bin()))
    print()
