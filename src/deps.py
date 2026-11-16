"""Startup check for the required external tools; offers to install missing ones."""

from __future__ import annotations

import shutil
import sys

from src.plat import get_config_dir

REQUIRED_TOOLS: list[str] = ["deno", "mpv", "ffmpeg"]


def print_cookies_help() -> None:
    conf = str(get_config_dir() / "config.yaml")
    print()
    print("\033[1;36mBrowser Authentication\033[0m")
    print()
    print("  TermTube reads cookies directly from your browser.")
    print("  Set the browser in your config or in Settings > Browser:")
    print()
    print(f"    Config: \033[36m{conf}\033[0m")
    print()
    print("    browser: auto       # auto-detect (default)")
    print("    browser: firefox    # use Firefox")
    print("    browser: chrome     # use Chrome (may require keychain access)")
    print("    browser: none       # unauthenticated mode")
    print()
    print("  You must be logged into YouTube in that browser.")
    print("  On macOS, Firefox is recommended (no keychain prompt).")
    print()


def check_dependencies() -> bool:
    """True if all required tools resolve on PATH (main.py puts the managed bin dir first).

    If any are missing and stdin is a TTY, offers to install them via src.bootstrap.
    """
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if not missing:
        return True

    print("\n\033[31m✗ Required tools missing:\033[0m")
    for tool in missing:
        print(f"  • {tool}")

    if not sys.stdin.isatty():
        _print_bootstrap_hint()
        return False

    return _offer_bootstrap(missing)


def _offer_bootstrap(missing: list[str]) -> bool:
    from src.bootstrap import get_deps_bin, install_tool

    print()
    print("  TermTube can download these from GitHub into:")
    print(f"    \033[36m{get_deps_bin()}\033[0m")
    print()

    try:
        ans = input("  Install missing tools now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans not in ("", "y", "yes"):
        _print_bootstrap_hint()
        return False

    all_ok = True
    for tool in missing:
        print(f"  Installing {tool}...", flush=True)
        if install_tool(tool, force=True):
            print(f"\033[32m  ✓ {tool} installed\033[0m")
        else:
            print(f"\033[31m  ✗ {tool} installation failed\033[0m")
            all_ok = False

    if all_ok:
        print()
    return all_ok


def _print_bootstrap_hint() -> None:
    from src.bootstrap import get_deps_bin

    print("\n  Install manually by running:")
    print("    \033[36mpython -m src.bootstrap\033[0m")
    print()
    print("  Or install individually:")
    print(f"    Target: {get_deps_bin()}")
    print()
