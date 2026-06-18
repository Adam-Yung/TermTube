"""Updater for TermTube system tools (yt-dlp, mpv, deno, ffmpeg).

Update policy: don't update until something breaks. When a tool failure is
detected, re-bootstrap that tool from GitHub releases. If it still fails
after update, suggest the user file a bug report.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from src.platform import IS_WINDOWS, IS_MACOS, IS_LINUX, get_cache_dir

# -- Constants -----------------------------------------------------------------

_CACHE_DIR: Path = get_cache_dir()
_LAST_VERSION: Path = _CACHE_DIR / "LAST_VERSION"
_LAST_COOKIE_REFRESH: Path = _CACHE_DIR / "LAST_COOKIE_REFRESH"



# -- Version tracking ----------------------------------------------------------

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
    the last update run, or None if unchanged / version undetectable.
    Called at TUI startup from a background timer in MainScreen.
    """
    current = get_ytdlp_version()
    if current is None:
        return None
    last = _read_last_version()
    if last is None:
        _write_last_version(current)
        return None
    if current != last:
        _write_last_version(current)
        return f"yt-dlp updated  {last} -> {current}"
    return None




def update_ytdlp(verbose: bool = False) -> bool:
    """Update yt-dlp to latest nightly. Returns True on success."""
    if not shutil.which("yt-dlp"):
        return False
    cmd = ["yt-dlp", "--update-to", "nightly"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            timeout=120,
        )
        if result.returncode == 0:
            new_ver = get_ytdlp_version()
            if new_ver:
                _write_last_version(new_ver)
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
            print("  No cookies_file configured -- skipping cookie refresh.")
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
        print(f"  Refreshing cookies from {browser}...", flush=True)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL if not verbose else None,
            timeout=120,
        )
    except FileNotFoundError:
        if verbose:
            print("  [!] yt-dlp not found -- cannot refresh cookies.")
        return False
    except subprocess.TimeoutExpired:
        if verbose:
            print("  [!] Cookie extraction timed out.")
        _cleanup_tmp(tmp_path)
        return False
    except Exception as exc:
        if verbose:
            print(f"  [!] Cookie extraction failed: {exc}")
        _cleanup_tmp(tmp_path)
        return False

    if result.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
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


# -- Bootstrap-based update ----------------------------------------------------

def _safe_print(msg: str) -> None:
    """Print a message, falling back to ASCII-safe output on Windows cp1252."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def run_all_updates(verbose: bool = False) -> bool:
    """Re-bootstrap all tools from GitHub releases.

    Called directly for ``termtube --update`` (verbose=True, foreground).
    Returns True if all tools were successfully updated.
    """
    from src.bootstrap import install_all

    if verbose:
        _safe_print("  Re-downloading all tools from GitHub releases...")

    success = install_all(force=True)

    # Also try yt-dlp's own self-update for the absolute latest nightly
    if shutil.which("yt-dlp"):
        if verbose:
            _safe_print("  Running yt-dlp self-update...")
        try:
            result = subprocess.run(
                ["yt-dlp", "--update-to", "nightly"],
                capture_output=not verbose,
                timeout=120,
            )
            if result.returncode == 0:
                new_ver = get_ytdlp_version()
                if new_ver:
                    _write_last_version(new_ver)
                if verbose:
                    _safe_print(f"  [ok] yt-dlp updated to {new_ver or 'latest'}")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

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

    print("  Downloading latest TermTube...", flush=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="termtube_update_"))
    zip_path = tmp_dir / "main.zip"

    try:
        urllib.request.urlretrieve(zip_url, zip_path)
    except Exception as exc:
        print(f"  [!] Download failed: {exc}")
        sys.exit(1)

    print("  Extracting...", flush=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except Exception as exc:
        print(f"  [!] Extraction failed: {exc}")
        sys.exit(1)

    extracted = tmp_dir / "TermTube-main"
    if not extracted.exists():
        candidates = [d for d in tmp_dir.iterdir() if d.is_dir()]
        if candidates:
            extracted = candidates[0]
        else:
            print("  [!] Could not find extracted directory.")
            sys.exit(1)

    # Install requirements via venv pip
    if IS_WINDOWS:
        pip_exe = install_dir / ".venv" / "Scripts" / "pip.exe"
    else:
        pip_exe = install_dir / ".venv" / "bin" / "pip3"

    req_file = extracted / "requirements.txt"
    if pip_exe.exists() and req_file.exists():
        print("  Installing requirements...", flush=True)
        result = subprocess.run(
            [str(pip_exe), "install", "-r", str(req_file), "--quiet"],
            cwd=str(extracted),
        )
        if result.returncode != 0:
            print("  [!] pip install failed -- continuing anyway.", flush=True)

    # Run external tool updates via bootstrap
    print("  Updating external tools...", flush=True)
    run_all_updates(verbose=True)

    # Generate and execute copy script
    print("  Copying new source files...", flush=True)
    copy_files = "requirements.txt termtube termtube.cmd setup.sh setup.ps1 uninstall.sh uninstall.ps1"

    if IS_WINDOWS:
        script_path = tmp_dir / "_update.cmd"
        script_lines = [
            "@echo off\r\n",
            f'robocopy "{extracted}\\src" "{install_dir}\\src" /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul\r\n',
            "if %ERRORLEVEL% GEQ 8 (echo [!] Source copy failed & exit /b 1)\r\n",
        ]
        for f in copy_files.split():
            script_lines.append(
                f'if exist "{extracted}\\{f}" copy /y "{extracted}\\{f}" "{install_dir}\\" >nul\r\n'
            )
        script_lines.append("echo TermTube updated successfully.\r\n")
        script_path.write_text("".join(script_lines))
        result = subprocess.run(["cmd", "/c", str(script_path)], check=False)
        if result.returncode >= 8:
            print("  [!] File copy step failed.", flush=True)
            sys.exit(1)
        try:
            import shutil as _shutil
            _shutil.rmtree(str(tmp_dir), ignore_errors=True)
        except Exception:
            pass
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


# -- __main__ (direct invocation: python -m src.updater --run) ----------------

if __name__ == "__main__":
    if "--run" in sys.argv:
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        ok = run_all_updates(verbose=verbose)
        sys.exit(0 if ok else 1)
