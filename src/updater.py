"""Updates for the bundled tools, yt-dlp (pip) and the app code itself."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from src.plat import IS_WINDOWS

_GITHUB_REPO = "Adam-Yung/TermTube"


def get_ytdlp_version() -> str | None:
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except (ImportError, AttributeError):
        return None


def update_ytdlp(verbose: bool = False) -> bool:
    """Upgrade yt-dlp and yt-dlp-ejs with the pip of the running venv. True on success."""
    bin_dir = Path(sys.executable).parent
    if sys.platform == "win32":
        pip_path = bin_dir / "pip.exe"
    else:
        pip_path = bin_dir / "pip3"
    if not pip_path.exists():
        pip_path = bin_dir / "pip"

    cmd = [str(pip_path), "install", "-U", "yt-dlp", "yt-dlp-ejs", "--quiet"]
    try:
        result = subprocess.run(cmd, capture_output=not verbose, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _github_latest_release(repo: str) -> tuple[str, str] | None:
    """Return (tag_name, zip_url) for the latest GitHub release, or None."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TermTube-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    tag = data.get("tag_name", "").strip()
    if not tag:
        return None
    return tag, f"https://github.com/{repo}/archive/refs/tags/{tag}.zip"


def _read_installed_version(install_dir: Path) -> str:
    try:
        return (install_dir / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _swap_dir(extracted: Path, install_dir: Path, subdir: str) -> None:
    """Replace install_dir/subdir with the extracted copy via .new/.old siblings."""
    src = extracted / subdir
    if not src.is_dir():
        return
    dst = install_dir / subdir
    dst_new = install_dir / f"{subdir}.new"
    dst_old = install_dir / f"{subdir}.old"
    for stale in (dst_new, dst_old):
        if stale.exists():
            shutil.rmtree(str(stale))
    shutil.copytree(str(src), str(dst_new))
    if dst.exists():
        dst.rename(dst_old)
    dst_new.rename(dst)
    if dst_old.exists():
        shutil.rmtree(str(dst_old))


def _download_release(zip_url: str, tag: str, tmp_dir: Path) -> Path | None:
    """Download and unpack the release into ``tmp_dir``; the extracted project folder, or None if there is none."""
    zip_path = tmp_dir / "release.zip"
    req = urllib.request.Request(zip_url, headers={"User-Agent": "TermTube-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        zip_path.write_bytes(resp.read())

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_dir)

    # GitHub names the folder TermTube-<tag without leading v>.
    extracted = tmp_dir / f"TermTube-{tag.lstrip('v')}"
    if extracted.exists():
        return extracted
    return next((d for d in tmp_dir.iterdir() if d.is_dir() and d.name != "__MACOSX"), None)


def _install_requirements(install_dir: Path, req_file: Path) -> None:
    if IS_WINDOWS:
        pip_exe = install_dir / ".venv" / "Scripts" / "pip.exe"
    else:
        pip_exe = install_dir / ".venv" / "bin" / "pip3"
    if pip_exe.exists() and req_file.exists():
        subprocess.run([str(pip_exe), "install", "-r", str(req_file), "--quiet"], check=False)


def _apply_release(install_dir: Path, tag: str, zip_url: str, say: Callable[[str], None]) -> bool:
    """Swap in the release ``tag``. False (reported through ``say``) when anything fails."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="termtube_appupdate_"))
    try:
        extracted = _download_release(zip_url, tag, tmp_dir)
        if extracted is None:
            say("  [!] Could not find extracted directory.")
            return False
        for subdir in ("src", "scripts"):
            _swap_dir(extracted, install_dir, subdir)
        _install_requirements(install_dir, extracted / "requirements.txt")
        (install_dir / "VERSION").write_text(tag, encoding="utf-8")
        say(f"  [ok] app: updated to {tag}")
        return True
    except Exception as exc:
        say(f"  [!] App update failed: {exc}")
        return False
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


def update_app_code(install_dir: Path, *, verbose: bool = False) -> bool:
    """Replace src/ and scripts/ with the latest GitHub release.

    A VERSION of "dev" is never overwritten. True if up to date or updated.
    """
    say = _safe_print if verbose else _silent
    say("  Checking for TermTube app updates...")

    result = _github_latest_release(_GITHUB_REPO)
    if result is None:
        say("  [!] Could not reach GitHub to check for updates.")
        return False

    latest_tag, zip_url = result
    installed = _read_installed_version(install_dir)

    if installed == "dev":
        say("  [ok] app: dev install — skipping auto-update.")
        return True

    if installed == latest_tag:
        say(f"  [ok] app: already on {latest_tag}")
        return True

    say(f"  app: {installed or 'unknown'} → {latest_tag}")
    say("  Downloading update...")
    return _apply_release(install_dir, latest_tag, zip_url, say)


def _silent(msg: str) -> None:
    """The ``say`` of a quiet run."""


def _safe_print(msg: str) -> None:
    """Print, degrading to ASCII on consoles that cannot encode it (Windows cp1252)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def run_all_updates(verbose: bool = False) -> bool:
    """Re-download all bundled tools, upgrade yt-dlp, update app code. True if all succeeded."""
    from src.bootstrap import install_all

    install_dir = Path(__file__).parent.parent
    say = _safe_print if verbose else _silent

    say("  Re-downloading all tools from GitHub releases...")
    success = install_all(force=True)

    say("  Updating yt-dlp via pip...")
    if not update_ytdlp(verbose=verbose):
        success = False
    elif verbose:
        _safe_print(f"  [ok] yt-dlp {get_ytdlp_version() or 'updated'}")

    if not update_app_code(install_dir, verbose=verbose):
        success = False

    say("  All tools updated successfully." if success else "  Some updates failed -- check output above.")
    return success


def self_update() -> bool:
    """Entry for ``termtube --update``: tools, yt-dlp and app code. True if every step succeeded."""
    _safe_print("  Updating TermTube...")
    return run_all_updates(verbose=True)


if __name__ == "__main__":
    if "--run" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        sys.exit(0 if run_all_updates(verbose=verbose) else 1)
