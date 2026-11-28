"""Release lookups and file downloads for the installer, with the advice printed when they fail. Stdlib only."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from src.plat import IS_LINUX, IS_MACOS

try:
    import ssl
except ImportError:
    ssl = None

_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds
_HEADERS = {"User-Agent": "TermTube-Bootstrap/1.0"}

# (text looked for in the lowered error, reason shown)
_CONNECTION_ERRORS = (
    ("refused", "Connection refused"),
    ("reset", "Connection reset"),
    ("network is unreachable", "Network is unreachable"),
)

_ADVICE = {
    "ssl": (
        "    • You may be behind a corporate proxy/firewall that intercepts HTTPS",
        "    • Disconnect from VPN or corporate network and retry",
    ),
    "timeout": ("    • Check your internet connection", "    • Disconnect from VPN/proxy and retry"),
    "connection": (
        "    • Check your internet connection and firewall settings",
        "    • Disconnect from VPN/proxy and retry",
    ),
    "other": ("    • Check your internet connection",),
}


def _classify_download_error(exc: Exception) -> tuple[str, str]:
    """Return (brief_reason, category); category is 'ssl', 'timeout', 'connection' or 'other'."""
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, Exception):
        exc = exc.reason
    exc_str = str(exc)
    low = exc_str.lower()

    if ssl is not None:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return "SSL certificate verification failed", "ssl"
        if isinstance(exc, ssl.SSLError):
            return f"SSL error: {exc_str}", "ssl"
    if "CERTIFICATE_VERIFY_FAILED" in exc_str.upper() or "SSL" in exc_str.upper():
        return f"SSL/TLS error: {exc_str}", "ssl"

    # URLError is an OSError, so this covers both.
    if isinstance(exc, OSError) and "timed out" in low:
        return "Connection timed out", "timeout"

    for marker, reason in _CONNECTION_ERRORS:
        if marker in low:
            return reason, "connection"
    return exc_str, "other"


def _print_download_guidance(dep_name: str, brief_error: str, category: str) -> None:
    lines = ["", f"  ⚠ Failed to download {dep_name}: {brief_error}", "", "  Possible fixes:", *_ADVICE[category]]
    if IS_MACOS:
        lines.append(f"    • Install manually via Homebrew: brew install {dep_name}")
    elif IS_LINUX:
        lines.append(f"    • Install manually via your package manager (e.g. apt install {dep_name})")

    lines += ["    • Run: termtube --update  (to retry later)", ""]
    print("\n".join(lines), file=sys.stderr, flush=True)


def _save_response(resp, tmp_dest: Path, label: str) -> int:
    """Stream ``resp`` into ``tmp_dest`` with a progress line. Returns the number of bytes written."""
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    with open(tmp_dest, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0 and sys.stdout.isatty():
                pct = downloaded * 100 // total
                print(f"\r    Downloading {label}... {pct}%", end="", flush=True)
    if sys.stdout.isatty():
        print(f"\r    Downloading {label}... done ({downloaded // 1024 // 1024}MB)", flush=True)
    else:
        print(f"    Downloaded {label} ({downloaded // 1024 // 1024}MB)", flush=True)
    return downloaded


def _attempt(url: str, dest: Path, tmp_dest: Path, label: str) -> bool:
    """One download into ``dest``; False for a short read. Network and file errors raise."""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)
        downloaded = _save_response(resp, tmp_dest, label)

    if total > 0 and downloaded < total:
        print(f"    [!] Incomplete download: got {downloaded} of {total} bytes", flush=True)
        tmp_dest.unlink(missing_ok=True)
        return False

    os.replace(tmp_dest, dest)
    return True


def download(url: str, dest: Path, *, desc: str = "", retries: int = _MAX_RETRIES) -> bool:
    """Download url to dest with retries. True on success.

    Writes a .tmp sibling and os.replace()s it, so an interrupted download never clobbers an existing binary.
    """
    label = desc or url.split("/")[-1]
    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")

    for attempt in range(1, retries + 1):
        if attempt > 1:
            print(f"    Retry {attempt}/{retries}...", flush=True)
            time.sleep(_RETRY_DELAY * attempt)

        print(f"    Downloading {label}...", flush=True)
        try:
            if _attempt(url, dest, tmp_dest, label):
                return True
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            tmp_dest.unlink(missing_ok=True)
            brief, category = _classify_download_error(exc)
            print(flush=True)
            print(f"    [!] Download failed: {brief}", flush=True)
            if attempt == retries:
                _print_download_guidance(label, brief, category)

    return False


def _tag_from_api(owner: str, repo: str) -> str | None:
    """Latest tag from the GitHub API. Uses ``GITHUB_TOKEN`` if set (the token goes to api.github.com only)."""
    headers = dict(_HEADERS)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("tag_name")


def _tag_from_redirect(owner: str, repo: str) -> str | None:
    """Latest tag from where ``/releases/latest`` redirects (``.../releases/tag/<tag>``); not API rate-limited."""
    req = urllib.request.Request(f"https://github.com/{owner}/{repo}/releases/latest", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        match = re.search(r"/releases/tag/([^/?#]+)$", resp.geturl())
    return urllib.parse.unquote(match.group(1)) if match else None


def github_latest_tag(owner: str, repo: str) -> str | None:
    """Latest release tag: the API first, then the release page's redirect when the API is rate-limited or down."""
    try:
        tag = _tag_from_api(owner, repo)
        if tag:
            return tag
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        brief = _classify_download_error(exc)[0]
        print(f"    [!] GitHub API request failed ({brief}); trying the release page", flush=True)
    try:
        return _tag_from_redirect(owner, repo)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        brief, category = _classify_download_error(exc)
        print(f"    [!] GitHub release lookup failed: {brief}", file=sys.stderr, flush=True)
        if category == "ssl":
            print("    (Likely behind a corporate proxy — see error guidance below)", file=sys.stderr, flush=True)
        return None
