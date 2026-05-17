"""Background and foreground updater for TermTube system tools.

Manages two sentinel files in the cache directory:
  UPDATING     — written at the start of an update run; removed on success.
  LAST_UPDATED — written only after a fully successful run.

Staleness rules (_needs_update):
  • UPDATING exists and is < UPDATING_TIMEOUT_S old → update in progress, skip.
  • LAST_UPDATED exists and is < UPDATE_INTERVAL_S old → still fresh, skip.
  • Anything else (either file missing, either file stale) → run updates.

A stale UPDATING (older than UPDATING_TIMEOUT_S) means the previous forked
process crashed or lost network mid-way; we re-run on the next exit.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from src.platform import IS_WINDOWS, IS_MACOS, IS_LINUX, get_cache_dir

# ── Platform-specific process creation flags ──────────────────────────────────
if IS_WINDOWS:
    _DETACHED_PROCESS: int = subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    _CREATE_NEW_PROCESS_GROUP: int = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
else:
    _DETACHED_PROCESS = 0x00000008
    _CREATE_NEW_PROCESS_GROUP = 0x00000200

# ── Constants ──────────────────────────────────────────────────────────────────

UPDATE_INTERVAL_S: int = 7 * 24 * 3600   # 1 week between automatic updates
UPDATING_TIMEOUT_S: int = 30 * 60        # 30 min: treat UPDATING as stale after this

_CACHE_DIR: Path = get_cache_dir()
_UPDATING: Path = _CACHE_DIR / "UPDATING"
_LAST_UPDATED: Path = _CACHE_DIR / "LAST_UPDATED"
_LAST_VERSION: Path = _CACHE_DIR / "LAST_VERSION"
_LAST_COOKIE_REFRESH: Path = _CACHE_DIR / "LAST_COOKIE_REFRESH"


# ── Sentinel helpers ───────────────────────────────────────────────────────────

def _mtime(path: Path) -> float | None:
    """Return mtime of *path*, or None if it does not exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _needs_update() -> bool:
    """Return True if an update run should be started."""
    now = time.time()

    mtime_updating = _mtime(_UPDATING)
    if mtime_updating is not None:
        age = now - mtime_updating
        if age < UPDATING_TIMEOUT_S:
            # A recent UPDATING file means another process is already running.
            return False
        # Stale UPDATING → previous run crashed; re-run unconditionally.
        return True

    mtime_last = _mtime(_LAST_UPDATED)
    if mtime_last is not None and (now - mtime_last) < UPDATE_INTERVAL_S:
        # Successfully updated within the last week.
        return False

    return True


def _write_updating() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _UPDATING.touch()


def _write_last_updated() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_UPDATED.touch()


def _remove_updating() -> None:
    try:
        _UPDATING.unlink()
    except FileNotFoundError:
        pass


# ── Version tracking ───────────────────────────────────────────────────────────

def get_ytdlp_version() -> str | None:
    """Return the currently installed yt-dlp version string, or None on failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _read_last_version() -> str | None:
    """Return the yt-dlp version recorded after the last successful update, or None."""
    try:
        return _LAST_VERSION.read_text().strip() or None
    except FileNotFoundError:
        return None


def _write_last_version(version: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_VERSION.write_text(version)


def check_for_update_notification() -> str | None:
    """Compare current yt-dlp version against the recorded post-update version.

    Returns a human-readable notification string if the version changed since
    the last update run (i.e., the update succeeded and the binary is newer),
    or None if unchanged / version undetectable.

    Intended to be called at TUI startup (from a background timer in MainScreen)
    so the version subprocess doesn't block the event loop.
    """
    current = get_ytdlp_version()
    if current is None:
        return None
    last = _read_last_version()
    if last is None:
        # First run after installing — record version, no notification.
        _write_last_version(current)
        return None
    if current != last:
        _write_last_version(current)
        return f"yt-dlp updated  {last} → {current}"
    return None


# ── Cookie refresher ──────────────────────────────────────────────────────────

def _load_config_lazy():
    """Import Config lazily to avoid circular imports in the background fork."""
    from src.config import Config
    return Config()


_RICK_ROLL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
def refresh_cookies(config=None, verbose: bool = False, link=_RICK_ROLL) -> bool:
    """Extract cookies from the configured browser into cookies_file.

    Writes to a .tmp file first, then atomically renames on success.
    Existing cookies.txt is preserved on failure.
    Returns True on success.
    """
    if config is None:
        config = _load_config_lazy()

    path = config.cookies_file_path
    if path is None:
        if verbose:
            print("  No cookies_file configured — skipping cookie refresh.")
        return False

    browser = config.get("browser") or "chrome"
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(".tmp")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser,
        "--cookies", str(tmp_path),
        "--skip-download",
        "--no-playlist",
        "--quiet",
        _RICK_ROLL,
    ]

    if verbose:
        print(f"  Refreshing cookies from {browser}…", flush=True)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL if not verbose else None,
            timeout=120,
        )
    except FileNotFoundError:
        if verbose:
            print("  ⚠  yt-dlp not found — cannot refresh cookies.")
        return False
    except subprocess.TimeoutExpired:
        if verbose:
            print("  ⚠  Cookie extraction timed out.")
        _cleanup_tmp(tmp_path)
        return False
    except Exception as exc:
        if verbose:
            print(f"  ⚠  Cookie extraction failed: {exc}")
        _cleanup_tmp(tmp_path)
        return False

    if result.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
        try:
            tmp_path.replace(path)
        except OSError:
            # Windows: target may be locked; fall back to remove+rename
            try:
                path.unlink(missing_ok=True)
                tmp_path.rename(path)
            except OSError:
                _cleanup_tmp(tmp_path)
                return False
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _LAST_COOKIE_REFRESH.touch()
        if verbose:
            print(f"  ✓  Cookies saved to {path}")
        return True

    if verbose:
        print("  ⚠  Cookie extraction produced no output.")
    _cleanup_tmp(tmp_path)
    return False


def _cleanup_tmp(tmp_path: Path) -> None:
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        pass


# ── Update command list ────────────────────────────────────────────────────────

def _update_commands() -> list[list[str]]:
    """Return the list of update commands for the current platform.

    Each entry is a argv list ready for subprocess.run / subprocess.Popen.
    Commands are ordered: yt-dlp first (most critical), then Deno, then the
    heavier media tools that change rarely.
    """
    cmds: list[list[str]] = []

    # yt-dlp — self-updates its own binary regardless of how it was installed.
    # Use --update-to nightly for maximum YouTube extractor freshness.
    if shutil.which("yt-dlp"):
        cmds.append(["yt-dlp", "--update-to", "nightly"])

    if IS_MACOS and shutil.which("brew"):
        cmds.append(["brew", "upgrade", "deno"])
        cmds.append(["brew", "upgrade", "mpv"])
        cmds.append(["brew", "upgrade", "ffmpeg"])
        cmds.append(["brew", "upgrade", "chafa"])
    elif IS_WINDOWS:
        winget = shutil.which("winget")
        if winget:
            def _winget_upgrade(pkg_id: str) -> list[str]:
                return [
                    "winget", "upgrade", "--id", pkg_id,
                    "--accept-source-agreements", "--accept-package-agreements",
                ]
            cmds.append(_winget_upgrade("DenoLand.Deno"))
            cmds.append(_winget_upgrade("Gyan.FFmpeg"))
            cmds.append(_winget_upgrade("hpjansson.Chafa"))
    elif IS_LINUX:
        # Linux: mpv, ffmpeg, chafa all need sudo — skip them.
        # Deno has its own self-updater that requires no privileges.
        if shutil.which("deno"):
            cmds.append(["deno", "upgrade"])

    return cmds


# ── Core update runner (synchronous) ──────────────────────────────────────────

def run_all_updates(verbose: bool = False) -> bool:
    """Run all update commands synchronously.

    Called directly for ``termtube --update`` (verbose=True, foreground) and
    by the forked ``--background`` process (verbose=False, detached).

    Returns True if all commands succeeded (or were skipped because the tool
    was not installed), False if any command returned a non-zero exit code.
    """
    _write_updating()
    all_ok = True

    for cmd in _update_commands():
        tool = cmd[0]
        if verbose:
            print(f"  Updating {tool}…", flush=True)
        try:
            if verbose:
                result = subprocess.run(cmd)
            else:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **({"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}),
                )
            if result.returncode != 0:
                if verbose:
                    print(f"  ⚠  {tool} update exited {result.returncode}", flush=True)
                all_ok = False
        except FileNotFoundError:
            # Tool not on PATH — skip silently.
            pass
        except Exception as exc:
            if verbose:
                print(f"  ⚠  {tool}: {exc}", flush=True)
            all_ok = False

    if all_ok:
        _write_last_updated()
        _remove_updating()
        # Record the newly installed yt-dlp version so the next launch can
        # detect the change and show a notification.
        new_ver = get_ytdlp_version()
        if new_ver:
            _write_last_version(new_ver)
    # On failure we leave UPDATING in place; it will be detected as stale on
    # the next exit and trigger a fresh attempt.

    # Refresh cookies using the (possibly freshly-updated) yt-dlp.
    # Non-fatal: failure here doesn't affect the overall update result.
    refresh_cookies(_load_config_lazy(), verbose=verbose)

    return all_ok


# ── Self-update (termtube --update) ────────────────────────────────────────────

def self_update() -> None:
    """Download latest TermTube source from GitHub and replace the current install.

    Steps:
      1. Download main.zip from GitHub
      2. Extract to a temp directory
      3. Install Python requirements via pip in the venv
      4. Run run_all_updates(verbose=True) for external tools
      5. Generate and execute a platform script to copy new source files over
    """
    import os
    import tempfile
    import urllib.request
    import zipfile

    install_dir = Path(__file__).parent.parent
    zip_url = "https://github.com/Adam-Yung/TermTube/archive/refs/heads/main.zip"

    print("  Downloading latest TermTube…", flush=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="termtube_update_"))
    zip_path = tmp_dir / "main.zip"

    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as exc:
        print(f"  ⚠  Download failed: {exc}")
        sys.exit(1)

    print("  Extracting…", flush=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except Exception as exc:
        print(f"  ⚠  Extraction failed: {exc}")
        sys.exit(1)

    extracted = tmp_dir / "TermTube-main"
    if not extracted.exists():
        candidates = [d for d in tmp_dir.iterdir() if d.is_dir()]
        if candidates:
            extracted = candidates[0]
        else:
            print("  ⚠  Could not find extracted directory.")
            sys.exit(1)

    # Install requirements via venv pip
    if IS_WINDOWS:
        pip_exe = install_dir / ".venv" / "Scripts" / "pip.exe"
    else:
        pip_exe = install_dir / ".venv" / "bin" / "pip3"

    req_file = extracted / "requirements.txt"
    if pip_exe.exists() and req_file.exists():
        print("  Installing requirements…", flush=True)
        subprocess.run(
            [str(pip_exe), "install", "-r", str(req_file), "--quiet"],
            cwd=str(extracted),
        )

    # Run external tool updates
    print("  Updating external tools…", flush=True)
    run_all_updates(verbose=True)

    # Generate and execute copy script
    print("  Copying new source files…", flush=True)
    copy_files = "requirements.txt termtube termtube.cmd setup.sh setup.ps1 uninstall.sh uninstall.ps1"

    if IS_WINDOWS:
        script_path = tmp_dir / "_update.cmd"
        script_content = (
            "@echo off\r\n"
            f'xcopy /s /y /q "{extracted}\\src" "{install_dir}\\src\\"\r\n'
        )
        for f in copy_files.split():
            script_content += (
                f'if exist "{extracted}\\{f}" copy /y "{extracted}\\{f}" "{install_dir}\\" >nul\r\n'
            )
        script_content += (
            f'rmdir /s /q "{tmp_dir}"\r\n'
            "echo TermTube updated successfully.\r\n"
        )
        script_path.write_text(script_content)
        subprocess.run(["cmd", "/c", str(script_path)], check=False)
        sys.exit(0)
    else:
        script_path = tmp_dir / "_update.sh"
        script_content = (
            "#!/bin/bash\n"
            f'cp -rf "{extracted}/src" "{install_dir}/"\n'
        )
        for f in copy_files.split():
            script_content += (
                f'[ -f "{extracted}/{f}" ] && cp -f "{extracted}/{f}" "{install_dir}/"\n'
            )
        script_content += (
            f'rm -rf "{tmp_dir}"\n'
            'echo "TermTube updated successfully."\n'
        )
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        os.execv("/bin/bash", ["/bin/bash", str(script_path)])


# ── Forked background entry point ─────────────────────────────────────────────

def maybe_update() -> None:
    """Check sentinel files and fork a detached updater process if stale.

    Called from main.py's ``finally`` block after ``app.run()`` returns.
    Returns immediately; the spawned process continues independently.
    """
    if not _needs_update():
        return

    cmd = [sys.executable, "-m", "src.updater", "--background"]

    if IS_WINDOWS:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP),
            close_fds=True,
        )
    else:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )


# ── __main__ (invoked by the forked background process) ───────────────────────

if __name__ == "__main__":
    if "--background" in sys.argv:
        run_all_updates(verbose=False)
