"""Dependency checker — validates tools and offers bootstrap installation."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from src.plat import IS_WINDOWS, IS_MACOS, get_config_dir

# Required tools and their purposes
REQUIRED_TOOLS: list[str] = ["deno", "mpv", "ffmpeg"]
OPTIONAL_TOOLS: list[str] = []


def print_cookies_help() -> None:
    """Print browser authentication help."""
    from src.plat import get_config_dir
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


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _has_mpv() -> bool:
    """Check for mpv — PATH or TermTube's bundled standalone on Windows."""
    if _has("mpv"):
        return True
    if IS_WINDOWS:
        import os
        bundled = Path(os.environ.get("LOCALAPPDATA", "")) / "termtube-deps" / "bin" / "mpv.exe"
        return bundled.exists()
    return False


def check_dependencies() -> bool:
    """Check all deps. Returns True if all required deps are present.

    If tools are missing, offers to install them via the bootstrap system
    (downloading from GitHub releases into ~/.local/termtube-deps/bin/).
    """
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for tool in REQUIRED_TOOLS:
        if tool == "mpv":
            present = _has_mpv()
        else:
            present = _has(tool)
        if not present:
            missing_required.append(tool)

    for tool in OPTIONAL_TOOLS:
        if not _has(tool):
            missing_optional.append(tool)

    if missing_optional:
        print("\n\033[33m⚠ Optional tools not found:\033[0m")
        for tool in missing_optional:
            print(f"  • {tool}")
        print()

    if not missing_required and not missing_optional:
        return True

    if not missing_required:
        # Only optional tools missing — offer bootstrap but don't block
        if sys.stdin.isatty():
            _offer_bootstrap(missing_optional, required=False)
        return True

    print("\n\033[31m✗ Required tools missing:\033[0m")
    for tool in missing_required:
        print(f"  • {tool}")

    all_missing = missing_required + missing_optional
    if not sys.stdin.isatty():
        _print_bootstrap_hint(all_missing)
        return False

    return _offer_bootstrap(all_missing, required=True)


def _offer_bootstrap(missing: list[str], *, required: bool) -> bool:
    """Offer to install missing tools via the bootstrap system."""
    from src.bootstrap import get_deps_bin, install_tool

    print()
    print(f"  TermTube can download these from GitHub into:")
    print(f"    \033[36m{get_deps_bin()}\033[0m")
    print()

    try:
        prompt = "Install missing tools now? [Y/n] " if required else "Install optional tools? [y/N] "
        ans = input(f"  {prompt}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    default_yes = required
    if default_yes:
        accepted = ans in ("", "y", "yes")
    else:
        accepted = ans in ("y", "yes")

    if not accepted:
        if required:
            _print_bootstrap_hint(missing)
        return not required

    all_ok = True
    for tool in missing:
        print(f"  Installing {tool}...", flush=True)
        if install_tool(tool, force=True):
            print(f"\033[32m  ✓ {tool} installed\033[0m")
        else:
            print(f"\033[31m  ✗ {tool} installation failed\033[0m")
            if tool in REQUIRED_TOOLS:
                all_ok = False

    if all_ok:
        print()
    return all_ok


def _print_bootstrap_hint(missing: list[str]) -> None:
    """Print manual bootstrap instructions."""
    print("\n  Install manually by running:")
    print("    \033[36mpython -m src.bootstrap\033[0m")
    print()
    print("  Or install individually:")
    from src.bootstrap import get_deps_bin
    print(f"    Target: {get_deps_bin()}")
    print()
