"""Dependency checker — prompts user to install missing tools."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from src.platform import IS_WINDOWS, IS_MACOS, get_config_dir

# (tool_name, brew_formula, apt_package, winget_id, is_required)
DEPS: list[tuple[str, str, str, str | None, bool]] = [
    ("yt-dlp",  "yt-dlp",  "yt-dlp",  "yt-dlp.yt-dlp",   True),
    ("deno",    "deno",    "deno",    "DenoLand.Deno",    True),   # required by yt-dlp for YouTube (JS runtime)
    ("mpv",     "mpv",     "mpv",     None,               True),   # Windows: bundled by setup.ps1
    ("ffmpeg",  "ffmpeg",  "ffmpeg",  "Gyan.FFmpeg",      False),  # optional: audio conversion
]


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


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def print_cookies_help() -> None:
    global COOKIES_HELP
    if COOKIES_HELP is None:
        COOKIES_HELP = _build_cookies_help()
    print(COOKIES_HELP)


def _has_mpv() -> bool:
    """Check for mpv — PATH or TermTube's bundled standalone on Windows."""
    if _has("mpv"):
        return True
    if IS_WINDOWS:
        import os
        bundled = Path(os.environ.get("LOCALAPPDATA", "")) / "TermTube" / "mpv" / "mpv.exe"
        return bundled.exists()
    return False


def _brew_available() -> bool:
    return _has("brew")


def _winget_available() -> bool:
    return IS_WINDOWS and _has("winget")


def _install_brew(formula: str) -> bool:
    print(f"  Installing {formula} via Homebrew...", flush=True)
    result = subprocess.run(["brew", "install", formula], capture_output=False)
    return result.returncode == 0


def _install_winget(pkg_id: str) -> bool:
    print(f"  Installing {pkg_id} via winget...", flush=True)
    result = subprocess.run(
        ["winget", "install", "--id", pkg_id,
         "--accept-source-agreements", "--accept-package-agreements"],
        capture_output=False,
    )
    return result.returncode == 0


def check_dependencies(auto_install: bool = False) -> bool:
    """Check all deps. Returns True if all required deps are present."""
    missing_required: list[tuple[str, str, str | None]] = []
    missing_optional: list[tuple[str, str, str | None]] = []

    for tool, brew, apt, winget, required in DEPS:
        if tool == "mpv":
            present = _has_mpv()
        else:
            present = _has(tool)
        if not present:
            if required:
                missing_required.append((tool, brew, winget))
            else:
                missing_optional.append((tool, brew, winget))

    if missing_optional:
        print("\n\033[33m⚠ Optional tools not found:\033[0m")
        for tool, _, _ in missing_optional:
            note = ""
            print(f"  • {tool}  {note}")
        print()

    if not missing_required:
        return True

    print("\n\033[31m✗ Required tools missing:\033[0m")
    for tool, brew, winget in missing_required:
        print(f"  • {tool}")

    if _winget_available():
        if not sys.stdin.isatty():
            _print_manual_install(missing_required)
            return False
        print()
        try:
            ans = input("Install missing tools via winget? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"

        if ans in ("", "y", "yes"):
            all_ok = True
            for tool, _, winget in missing_required:
                if winget and _install_winget(winget):
                    print(f"\033[32m  ✓ Installed {tool}\033[0m")
                else:
                    print(f"\033[31m  ✗ Failed to install {tool}\033[0m")
                    all_ok = False
            return all_ok
        else:
            _print_manual_install(missing_required)
            return False
    elif _brew_available():
        if not sys.stdin.isatty():
            _print_manual_install(missing_required)
            return False
        print()
        try:
            ans = input("Install missing tools via Homebrew? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"

        if ans in ("", "y", "yes"):
            all_ok = True
            for tool, brew, _ in missing_required:
                if _install_brew(brew):
                    print(f"\033[32m  ✓ Installed {tool}\033[0m")
                else:
                    print(f"\033[31m  ✗ Failed to install {tool}\033[0m")
                    all_ok = False
            return all_ok
        else:
            _print_manual_install(missing_required)
            return False
    else:
        _print_manual_install(missing_required)
        return False


def _print_manual_install(missing: list[tuple[str, str, str | None]]) -> None:
    print("\nInstall manually:")
    if IS_WINDOWS:
        for tool, _, winget in missing:
            if tool == "yt-dlp":
                print("  # yt-dlp nightly (recommended):")
                print("  winget install yt-dlp.yt-dlp")
                print("  # or download from: github.com/yt-dlp/yt-dlp-nightly-builds/releases")
            elif tool == "deno":
                print("  winget install DenoLand.Deno")
            elif winget:
                print(f"  winget install {winget}")
            else:
                print(f"  (install {tool} manually)")
    else:
        for tool, brew, _ in missing:
            if tool == "yt-dlp":
                print("  # yt-dlp nightly (recommended):")
                print(
                    "  curl -fsSL https://github.com/yt-dlp/yt-dlp-nightly-builds"
                    "/releases/latest/download/yt-dlp \\"
                )
                print("       -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp")
            elif tool == "deno":
                print("  curl -fsSL https://deno.land/install.sh | sh")
            elif brew:
                fallback = f"sudo apt install {tool}  # or equivalent"
                print(f"  brew install {brew}" if _brew_available() else f"  {fallback}")

