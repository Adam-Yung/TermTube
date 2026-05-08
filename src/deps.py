"""TermTube v2 — dependency validation.

Checks required and optional system tools/Python packages.
Offers Homebrew/apt auto-install for missing required tools.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal


@dataclass
class DepResult:
    name: str
    required: bool
    found: bool
    version: str = ""
    install_hint: str = ""


def check_all() -> list[DepResult]:
    results = []

    # Required Python packages
    for pkg, import_name in [("yt-dlp", "yt_dlp"), ("textual", "textual"), ("yaml", "yaml")]:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "?")
            results.append(DepResult(pkg, required=True, found=True, version=ver))
        except ImportError:
            results.append(DepResult(
                pkg, required=True, found=False,
                install_hint=f"pip install {pkg}",
            ))

    # Optional Python packages
    try:
        import textual_image  # noqa: F401
        results.append(DepResult("textual-image", required=False, found=True))
    except ImportError:
        results.append(DepResult(
            "textual-image", required=False, found=False,
            install_hint="pip install textual-image (optional: Kitty/Sixel thumbnails)",
        ))

    # Required system binaries
    for tool in ["mpv", "yt-dlp"]:
        path = shutil.which(tool)
        if path:
            try:
                out = subprocess.run(
                    [tool, "--version"], capture_output=True, text=True, timeout=5
                )
                ver = out.stdout.splitlines()[0] if out.stdout else "?"
            except Exception:
                ver = "?"
            results.append(DepResult(tool, required=True, found=True, version=ver))
        else:
            hint = _install_hint(tool)
            results.append(DepResult(tool, required=True, found=False, install_hint=hint))

    # Optional system binaries
    for tool in ["ffmpeg"]:
        path = shutil.which(tool)
        results.append(DepResult(
            tool, required=False, found=bool(path),
            install_hint=_install_hint(tool) if not path else "",
        ))

    return results


def assert_required(results: list[DepResult] | None = None) -> None:
    """Raise SystemExit if any required dep is missing."""
    if results is None:
        results = check_all()
    missing = [r for r in results if r.required and not r.found]
    if missing:
        print("TermTube: missing required dependencies:\n")
        for r in missing:
            print(f"  ✗  {r.name}")
            if r.install_hint:
                print(f"       → {r.install_hint}")
        print()
        sys.exit(1)


def _install_hint(tool: str) -> str:
    platform = sys.platform
    hints = {
        "mpv": {
            "darwin": "brew install mpv",
            "linux":  "sudo apt install mpv  (or dnf/pacman equivalent)",
        },
        "yt-dlp": {
            "darwin": "pip install yt-dlp  (or brew install yt-dlp)",
            "linux":  "pip install yt-dlp",
        },
        "ffmpeg": {
            "darwin": "brew install ffmpeg",
            "linux":  "sudo apt install ffmpeg",
        },
    }
    platform_key = "darwin" if platform == "darwin" else "linux"
    return hints.get(tool, {}).get(platform_key, f"install {tool}")


def print_cookies_help() -> None:
    print("""
Cookie Setup — TermTube v2
==========================

Option 1 (recommended): Auto-fetch from browser
  termtube --setup-cookies          # interactive wizard
  termtube --setup-cookies chrome   # specify browser directly

Option 2: Export manually with yt-dlp
  yt-dlp --cookies-from-browser chrome --cookies ~/.config/TermTube/cookies.txt \\
         --skip-download https://www.youtube.com

Option 3: Use a browser extension
  Install "Get cookies.txt LOCALLY" in Chrome/Firefox.
  Export cookies for youtube.com.
  Copy the file to ~/.config/TermTube/cookies.txt

The cookies file is refreshed automatically when it's older than 7 days.
""")
