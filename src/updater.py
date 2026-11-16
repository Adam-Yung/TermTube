"""Updates for the bundled tools, yt-dlp (pip) and the app code itself."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
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


def update_app_code(install_dir: Path, *, verbose: bool = False) -> bool:
    """Replace src/ and scripts/ with the latest GitHub release.

    A VERSION of "dev" is never overwritten. True if up to date or updated.
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

        # GitHub names the folder TermTube-<tag without leading v>.
        extracted = tmp_dir / f"TermTube-{latest_tag.lstrip('v')}"
        if not extracted.exists():
            candidates = [d for d in tmp_dir.iterdir() if d.is_dir() and d.name != "__MACOSX"]
            extracted = candidates[0] if candidates else None
        if extracted is None or not extracted.exists():
            if verbose:
                _safe_print("  [!] Could not find extracted directory.")
            return False

        for subdir in ("src", "scripts"):
            _swap_dir(extracted, install_dir, subdir)

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

        (install_dir / "VERSION").write_text(latest_tag, encoding="utf-8")
        if verbose:
            _safe_print(f"  [ok] app: updated to {latest_tag}")
        return True

    except Exception as exc:
        if verbose:
            _safe_print(f"  [!] App update failed: {exc}")
        return False
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


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

    if verbose:
        _safe_print("  Re-downloading all tools from GitHub releases...")

    success = install_all(force=True)

    if verbose:
        _safe_print("  Updating yt-dlp via pip...")
    ytdlp_ok = update_ytdlp(verbose=verbose)
    if ytdlp_ok and verbose:
        _safe_print(f"  [ok] yt-dlp {get_ytdlp_version() or 'updated'}")
    if not ytdlp_ok:
        success = False

    if not update_app_code(install_dir, verbose=verbose):
        success = False

    if verbose:
        if success:
            _safe_print("  All tools updated successfully.")
        else:
            _safe_print("  Some updates failed -- check output above.")

    return success


def self_update() -> bool:
    """Entry for ``termtube --update``: tools, yt-dlp and app code. True if every step succeeded."""
    _safe_print("  Updating TermTube...")
    return run_all_updates(verbose=True)


if __name__ == "__main__":
    if "--run" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        sys.exit(0 if run_all_updates(verbose=verbose) else 1)
