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

# ── Constants ──────────────────────────────────────────────────────────────────

UPDATE_INTERVAL_S: int = 7 * 24 * 3600   # 1 week between automatic updates
UPDATING_TIMEOUT_S: int = 30 * 60        # 30 min: treat UPDATING as stale after this

_CACHE_DIR: Path = get_cache_dir()
_UPDATING: Path = _CACHE_DIR / "UPDATING"
_LAST_UPDATED: Path = _CACHE_DIR / "LAST_UPDATED"
_LAST_VERSION: Path = _CACHE_DIR / "LAST_VERSION"


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
        # Stale UPDATING → previous run failed; fall through to re-run.

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
            cmds.append(_winget_upgrade("mpv.net"))
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

    return all_ok


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
            creationflags=(
                subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            ),
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
