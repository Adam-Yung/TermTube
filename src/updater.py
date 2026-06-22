"""Updater for TermTube system tools (yt-dlp, mpv, deno, ffmpeg) and app code.

Update policy: don't update until something breaks. When a tool failure is
detected, re-bootstrap that tool from GitHub releases. If it still fails
after update, suggest the user file a bug report.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from src.plat import IS_WINDOWS, IS_MACOS, IS_LINUX, get_cache_dir

# -- Constants -----------------------------------------------------------------

_CACHE_DIR: Path = get_cache_dir()
_LAST_VERSION: Path = _CACHE_DIR / "LAST_VERSION"
_PENDING_VERSION_NOTIFY: Path = _CACHE_DIR / "PENDING_VERSION_NOTIFY"
_LAST_COOKIE_REFRESH: Path = _CACHE_DIR / "LAST_COOKIE_REFRESH"
_GITHUB_REPO = "Adam-Yung/TermTube"



# -- Version tracking ----------------------------------------------------------

def get_ytdlp_version() -> str | None:
    """Return the currently installed yt-dlp version string, or None."""
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except (ImportError, AttributeError):
        return None


def _read_last_version() -> str | None:
    try:
        return _LAST_VERSION.read_text().strip() or None
    except FileNotFoundError:
        return None


def _write_last_version(version: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_VERSION.write_text(version)


def check_for_update_notification() -> str | None:
    """Return a pending update notification string and clear it, or None.

    After update_ytdlp() succeeds it writes a PENDING_VERSION_NOTIFY file with
    the "old -> new" message.  We read and delete it here (called once at startup)
    so the notification fires exactly once without spawning yt-dlp --version.
    """
    if not _PENDING_VERSION_NOTIFY.exists():
        return None
    try:
        msg = _PENDING_VERSION_NOTIFY.read_text().strip()
        _PENDING_VERSION_NOTIFY.unlink(missing_ok=True)
        return msg or None
    except OSError:
        return None




def update_ytdlp(verbose: bool = False) -> bool:
    """Update yt-dlp and yt-dlp-ejs to latest via pip. Returns True on success."""
    old_ver = get_ytdlp_version()

    # Find pip in same venv as current Python
    if sys.platform == "win32":
        pip_path = Path(sys.executable).parent / "pip.exe"
    else:
        pip_path = Path(sys.executable).parent / "pip3"
    if not pip_path.exists():
        pip_path = Path(sys.executable).parent / "pip"

    cmd = [str(pip_path), "install", "-U", "yt-dlp", "yt-dlp-ejs", "--quiet"]
    try:
        result = subprocess.run(cmd, capture_output=not verbose, timeout=120)
        if result.returncode == 0:
            new_ver = get_ytdlp_version()
            if new_ver:
                _write_last_version(new_ver)
                if old_ver and new_ver != old_ver:
                    try:
                        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        _PENDING_VERSION_NOTIFY.write_text(
                            f"yt-dlp updated  {old_ver} -> {new_ver}"
                        )
                    except OSError:
                        pass
            return True
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False

# -- Cookie refresher ----------------------------------------------------------

def _load_config_lazy():
    """Import Config lazily to avoid circular imports in the background fork."""
    from src.config import Config
    return Config()


_RICK_ROLL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def refresh_cookies(config=None, verbose: bool = False, link=_RICK_ROLL, browser: str | None = None) -> bool:
    """Extract cookies from the configured browser into cookies_file.

    Writes to a .tmp file first, then atomically renames on success.
    Existing cookies.txt is preserved on failure.
    If *browser* is passed, it overrides both config and auto-detection.
    Returns True on success.
    """
    if config is None:
        config = _load_config_lazy()

    path = config.cookies_file_path
    if path is None:
        if verbose:
            print("  No cookies_file configured -- skipping cookie refresh.")
        return False

    from src.browsers import detect_installed_browsers, is_auto_browser, get_browser_label

    if browser:
        pass
    elif not is_auto_browser(config.get("browser")):
        browser = config.get("browser")
    else:
        detected = detect_installed_browsers()
        if not detected:
            if verbose:
                print("  [!] No supported browsers detected on this system.")
                print("  Set 'browser' in config to one of: brave, chrome, chromium, edge, firefox, opera, safari, vivaldi, whale")
            return False
        if len(detected) == 1:
            browser = detected[0]["name"]
            if verbose:
                print(f"  Auto-detected browser: {get_browser_label(browser)}")
        else:
            browser = detected[0]["name"]
            if verbose:
                print(f"  Auto-detected browser: {get_browser_label(browser)} (from {len(detected)} installed)")
    if not browser:
        browser = "chrome"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")

    if verbose:
        print(f"  Refreshing cookies from {browser}...", flush=True)

    try:
        import yt_dlp
        ydl_opts = {
            'cookiesfrombrowser': (browser, None, None, None),
            'cookiefile': str(tmp_path),
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(link, download=False)
    except ImportError:
        if verbose:
            print("  [!] yt-dlp not installed -- cannot refresh cookies.")
        return False
    except Exception as exc:
        if verbose:
            print(f"  [!] Cookie extraction failed: {exc}")
        _cleanup_tmp(tmp_path)
        return False

    if tmp_path.exists() and tmp_path.stat().st_size > 0:
        try:
            cookie_text = tmp_path.read_text(errors="replace")
        except OSError:
            _cleanup_tmp(tmp_path)
            return False

        has_youtube_cookies = any(
            line.strip() and not line.startswith("#")
            and (".youtube.com" in line or ".google.com" in line)
            for line in cookie_text.splitlines()
        )
        if not has_youtube_cookies:
            if verbose:
                print("  [!] Cookie extraction produced no YouTube session cookies.")
                print("  The browser may not be logged in, or the cookie store is locked.")
                print("  Try: termtube --cookies-help")
            _cleanup_tmp(tmp_path)
            return False

        try:
            tmp_path.replace(path)
        except OSError:
            try:
                path.unlink(missing_ok=True)
                tmp_path.rename(path)
            except OSError:
                _cleanup_tmp(tmp_path)
                return False
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _LAST_COOKIE_REFRESH.touch()
        if verbose:
            print(f"  Cookies saved to {path}")
        return True

    if verbose:
        print("  [!] Cookie extraction produced no output.")
    _cleanup_tmp(tmp_path)
    return False


def _cleanup_tmp(tmp_path: Path) -> None:
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        pass


# -- App code self-update ------------------------------------------------------

def _github_latest_release(repo: str) -> tuple[str, str] | None:
    """Return (tag_name, zip_url) for the latest GitHub release, or None."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TermTube-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            data = json.loads(resp.read())
            tag = data.get("tag_name", "").strip()
            if not tag:
                return None
            zip_url = f"https://github.com/{repo}/archive/refs/tags/{tag}.zip"
            return tag, zip_url
    except Exception:
        return None


def _read_installed_version(install_dir: Path) -> str:
    version_file = install_dir / "VERSION"
    try:
        return version_file.read_text().strip()
    except OSError:
        return ""


def update_app_code(install_dir: Path, *, verbose: bool = False) -> bool:
    """Download the latest TermTube release from GitHub and update src/ and scripts/.

    Skips if the installed VERSION matches the latest tag, or if VERSION is
    'dev' (developer installs never auto-update over themselves).
    Returns True if already up-to-date or update succeeded, False on failure.
    """
    if verbose:
        _safe_print("  Checking for TermTube app updates...")

    result = _github_latest_release(_GITHUB_REPO)
    if result is None:
        if verbose:
            _safe_print("  [!] Could not reach GitHub to check for updates.")
        return False

    latest_tag, zip_url = result
    installed = _read_installed_version(install_dir)

    if installed == "dev":
        if verbose:
            _safe_print("  [ok] app: dev install — skipping auto-update.")
        return True

    if installed == latest_tag:
        if verbose:
            _safe_print(f"  [ok] app: already on {latest_tag}")
        return True

    if verbose:
        _safe_print(f"  app: {installed or 'unknown'} → {latest_tag}")
        _safe_print("  Downloading update...")

    tmp_dir = Path(tempfile.mkdtemp(prefix="termtube_appupdate_"))
    zip_path = tmp_dir / "release.zip"
    try:
        req = urllib.request.Request(zip_url, headers={"User-Agent": "TermTube-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            zip_path.write_bytes(resp.read())

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)

        # GitHub names the extracted folder TermTube-{tag} (strips leading 'v')
        tag_stripped = latest_tag.lstrip("v")
        extracted = tmp_dir / f"TermTube-{tag_stripped}"
        if not extracted.exists():
            candidates = [d for d in tmp_dir.iterdir() if d.is_dir() and d.name != "__MACOSX"]
            extracted = candidates[0] if candidates else None
        if extracted is None or not extracted.exists():
            if verbose:
                _safe_print("  [!] Could not find extracted directory.")
            return False

        # Atomically replace src/ and scripts/
        for subdir in ("src", "scripts"):
            src = extracted / subdir
            dst = install_dir / subdir
            if not src.is_dir():
                continue
            dst_tmp = install_dir / f"{subdir}.new"
            dst_old = install_dir / f"{subdir}.old"
            if dst_tmp.exists():
                shutil.rmtree(str(dst_tmp))
            shutil.copytree(str(src), str(dst_tmp))
            if dst_old.exists():
                shutil.rmtree(str(dst_old))
            if dst.exists():
                dst.rename(dst_old)
            dst_tmp.rename(dst)
            if dst_old.exists():
                shutil.rmtree(str(dst_old))

        # Re-run pip if requirements.txt changed
        req_file = extracted / "requirements.txt"
        if IS_WINDOWS:
            pip_exe = install_dir / ".venv" / "Scripts" / "pip.exe"
        else:
            pip_exe = install_dir / ".venv" / "bin" / "pip3"
        if pip_exe.exists() and req_file.exists():
            subprocess.run(
                [str(pip_exe), "install", "-r", str(req_file), "--quiet"],
                check=False,
            )

        # Write new version
        (install_dir / "VERSION").write_text(latest_tag)
        if verbose:
            _safe_print(f"  [ok] app: updated to {latest_tag}")
        return True

    except Exception as exc:
        if verbose:
            _safe_print(f"  [!] App update failed: {exc}")
        return False
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


# -- Bootstrap-based update ----------------------------------------------------

def _safe_print(msg: str) -> None:
    """Print a message, falling back to ASCII-safe output on Windows cp1252."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def run_all_updates(verbose: bool = False) -> bool:
    """Re-bootstrap all tools from GitHub releases and update app code.

    Called directly for ``termtube --update`` (verbose=True, foreground).
    Returns True if all tools were successfully updated.
    """
    from src.bootstrap import install_all

    install_dir = Path(__file__).parent.parent

    if verbose:
        _safe_print("  Re-downloading all tools from GitHub releases...")

    success = install_all(force=True)

    # Update yt-dlp and yt-dlp-ejs via pip
    if verbose:
        _safe_print("  Updating yt-dlp via pip...")
    ytdlp_ok = update_ytdlp(verbose=verbose)
    if ytdlp_ok and verbose:
        ver = get_ytdlp_version()
        _safe_print(f"  [ok] yt-dlp {ver or 'updated'}")

    # Update app code from latest GitHub release
    app_ok = update_app_code(install_dir, verbose=verbose)
    if not app_ok:
        success = False

    if verbose:
        if success:
            _safe_print("  All tools updated successfully.")
        else:
            _safe_print("  Some updates failed -- check output above.")

    return success


def update_tool(name: str, verbose: bool = False) -> bool:
    """Re-bootstrap a single tool. Called on failure detection."""
    from src.bootstrap import install_tool

    if verbose:
        _safe_print(f"  Re-downloading {name} from GitHub releases...")

    return install_tool(name, force=True)


# -- Self-update (termtube --update) ------------------------------------------

def self_update() -> None:
    """Update TermTube app code and all tools. Delegates to update_app_code + run_all_updates."""
    install_dir = Path(__file__).parent.parent
    _safe_print("  Updating TermTube...")
    update_app_code(install_dir, verbose=True)
    run_all_updates(verbose=True)


# -- __main__ (direct invocation: python -m src.updater --run) ----------------

if __name__ == "__main__":
    if "--run" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        ok = run_all_updates(verbose=verbose)
        sys.exit(0 if ok else 1)
