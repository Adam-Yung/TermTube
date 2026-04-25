"""Dependency checker — prompts user to install missing tools."""

from __future__ import annotations

import shutil
import subprocess
import sys

# (tool_name, brew_formula, apt_package, is_required)
DEPS: list[tuple[str, str, str, bool]] = [
    ("yt-dlp",  "yt-dlp",  "yt-dlp",  True),
    ("mpv",     "mpv",     "mpv",     True),
    ("chafa",   "chafa",   "chafa",   False),  # optional: thumbnails
    ("ffmpeg",  "ffmpeg",  "ffmpeg",  False),  # optional: audio conversion
]

COOKIES_HELP = """
\033[1;36mHow to get a cookies.txt file\033[0m
\033[90m──────────────────────────────────────────────\033[0m

\033[1mOption A — Browser extension (manual)\033[0m

  Chrome / Edge:
    Install "Get cookies.txt LOCALLY" from the Chrome Web Store
    chrome.google.com/webstore → search: Get cookies.txt LOCALLY

  Firefox:
    Install "cookies.txt" from Firefox Add-ons
    addons.mozilla.org → search: cookies.txt

  Then visit youtube.com, click the extension icon,
  and export in Netscape format. Save to:

    ~/.config/TermTube/cookies.txt

\033[90m──────────────────────────────────────────────\033[0m

\033[1mOption B — Export via yt-dlp\033[0m

  Run this once (fast, no video downloaded):

    yt-dlp --cookies-from-browser chrome \\
           --cookies ~/.config/TermTube/cookies.txt \\
           --skip-download --quiet --no-warnings \\
           "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  Replace \033[36mchrome\033[0m with \033[36mfirefox\033[0m, \033[36mbrave\033[0m, or \033[36medge\033[0m as needed.

\033[90m──────────────────────────────────────────────\033[0m

\033[1mOption C — Browser session (simplest)\033[0m

  Skip cookies.txt and set in ~/.config/TermTube/config.yaml:

    cookies_file: null
    browser: chrome

  You must be logged into YouTube in that browser.
  Safari is sandboxed on macOS and is usually blocked.

\033[90m──────────────────────────────────────────────\033[0m
"""


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _brew_available() -> bool:
    return _has("brew")


def _install_brew(formula: str) -> bool:
    print(f"  Installing {formula} via Homebrew...", flush=True)
    result = subprocess.run(["brew", "install", formula], capture_output=False)
    return result.returncode == 0


def check_dependencies(auto_install: bool = False) -> bool:
    """Check all deps. Returns True if all required deps are present."""
    missing_required: list[tuple[str, str]] = []
    missing_optional: list[tuple[str, str]] = []

    for tool, brew, apt, required in DEPS:
        if not _has(tool):
            if required:
                missing_required.append((tool, brew))
            else:
                missing_optional.append((tool, brew))

    if missing_optional:
        print("\n\033[33m⚠ Optional tools not found:\033[0m")
        for tool, _ in missing_optional:
            note = "(thumbnails disabled)" if tool == "chafa" else ""
            print(f"  • {tool}  {note}")
        print()

    if not missing_required:
        return True

    print("\n\033[31m✗ Required tools missing:\033[0m")
    for tool, brew in missing_required:
        print(f"  • {tool}")

    if _brew_available():
        print()
        try:
            ans = input("Install missing tools via Homebrew? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"

        if ans in ("", "y", "yes"):
            all_ok = True
            for tool, brew in missing_required:
                if not _install_brew(brew):
                    print(f"\033[31m  ✗ Failed to install {tool}\033[0m")
                    all_ok = False
                else:
                    print(f"\033[32m  ✓ Installed {tool}\033[0m")
            return all_ok
        else:
            _print_manual_install(missing_required)
            return False
    else:
        _print_manual_install(missing_required)
        return False


def _print_manual_install(missing: list[tuple[str, str]]) -> None:
    print("\nInstall manually:")
    if _brew_available():
        formulas = " ".join(f for _, f in missing if f)
        print(f"  brew install {formulas}")
    else:
        print("  Install Homebrew first: https://brew.sh")
        formulas = " ".join(f for _, f in missing if f)
        print(f"  Then: brew install {formulas}")


def print_cookies_help() -> None:
    print(COOKIES_HELP)
