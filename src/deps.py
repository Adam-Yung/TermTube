"""Dependency checker — validates tools and offers bootstrap installation."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from src.platform import IS_WINDOWS, IS_MACOS, get_config_dir

# Required tools and their purposes
REQUIRED_TOOLS: list[str] = ["yt-dlp", "deno", "mpv", "ffmpeg"]
OPTIONAL_TOOLS: list[str] = []


def _build_cookies_help() -> str:
    """Build the --cookies-help text with platform-correct paths and shell syntax."""
    ck   = str(get_config_dir() / "cookies.txt")
    conf = str(get_config_dir() / "config.yaml")
    sep  = "\033[90m" + "─" * 46 + "\033[0m"

    if IS_WINDOWS:
        option_b_cmd = (
            f'  yt-dlp --cookies-from-browser chrome `\n'
            f'         --cookies "{ck}" `\n'
            f'         --skip-download --quiet --no-warnings `\n'
            f'         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"'
        )
    else:
        option_b_cmd = (
            f'  yt-dlp --cookies-from-browser chrome \\\n'
            f'         --cookies {ck} \\\n'
            f'         --skip-download --quiet --no-warnings \\\n'
            f'         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"'
        )

    return (
        f"\033[1;36mHow to get a cookies.txt file\033[0m\n"
        f"{sep}\n"
        f"\n"
        f"\033[1mOption A — Browser extension (manual)\033[0m\n"
        f"\n"
        f"  Chrome / Edge:\n"
        f'    Install "Get cookies.txt LOCALLY" from the Chrome Web Store\n'
        f"    chrome.google.com/webstore → search: Get cookies.txt LOCALLY\n"
        f"\n"
        f"  Firefox:\n"
        f'    Install "cookies.txt" from Firefox Add-ons\n'
        f"    addons.mozilla.org → search: cookies.txt\n"
        f"\n"
        f"  Then visit youtube.com, click the extension icon,\n"
        f"  and export in Netscape format. Save to:\n"
        f"\n"
        f"    {ck}\n"
        f"\n"
        f"{sep}\n"
        f"\n"
        f"\033[1mOption B — Export via yt-dlp\033[0m\n"
        f"\n"
        f"  Run this once (fast, no video downloaded):\n"
        f"\n"
        f"{option_b_cmd}\n"
        f"\n"
        f"  Replace \033[36mchrome\033[0m with \033[36mfirefox\033[0m, "
        f"\033[36mbrave\033[0m, or \033[36medge\033[0m as needed.\n"
        f"\n"
        f"{sep}\n"
        f"\n"
        f"\033[1mOption C — Browser session (simplest)\033[0m\n"
        f"\n"
        f"  Skip cookies.txt and set in {conf}:\n"
        f"\n"
        f"    cookies_file: null\n"
        f"    browser: chrome\n"
        f"\n"
        f"  You must be logged into YouTube in that browser.\n"
        f"  Safari is sandboxed on macOS and is usually blocked.\n"
        f"\n"
        f"{sep}\n"
    )


COOKIES_HELP: str | None = None


def print_cookies_help() -> None:
    global COOKIES_HELP
    if COOKIES_HELP is None:
        COOKIES_HELP = _build_cookies_help()
    print(COOKIES_HELP)


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _has_mpv() -> bool:
    """Check for mpv — PATH or TermTube's bundled standalone on Windows."""
    if _has("mpv"):
        return True
    if IS_WINDOWS:
        import os
        bundled = Path(os.environ.get("LOCALAPPDATA", "")) / "TermTube" / "mpv" / "mpv.exe"
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
