"""Dependency bootstrap — download and install binary dependencies from GitHub.

Only uses Python stdlib (urllib, zipfile, tarfile, json) so it can run
immediately after creating the venv, without any pip packages.

Install location: ~/.local/termtube-deps/bin/ (Unix) or %LOCALAPPDATA%/termtube-deps/bin/ (Windows)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


# ── Platform Detection ────────────────────────────────────────────────────────

def _detect_platform() -> tuple[str, str]:
    """Return (os_name, arch) normalized for download URL construction."""
    os_name = sys.platform
    if os_name == "darwin":
        os_name = "macos"
    elif os_name.startswith("linux"):
        os_name = "linux"
    elif os_name == "win32":
        os_name = "windows"

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        arch = machine

    return os_name, arch


OS_NAME, ARCH = _detect_platform()


# ── Paths ─────────────────────────────────────────────────────────────────────

def get_deps_dir() -> Path:
    """Root directory for TermTube-managed dependencies."""
    if OS_NAME == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local"
    return base / "termtube-deps"


def get_deps_bin() -> Path:
    """Binary directory containing all TermTube-managed executables."""
    return get_deps_dir() / "bin"


def _versions_file() -> Path:
    return get_deps_dir() / "versions.json"


def _read_versions() -> dict:
    vf = _versions_file()
    if vf.exists():
        try:
            return json.loads(vf.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_versions(data: dict) -> None:
    vf = _versions_file()
    vf.parent.mkdir(parents=True, exist_ok=True)
    vf.write_text(json.dumps(data, indent=2))


# ── Download helpers ──────────────────────────────────────────────────────────

def _download(url: str, dest: Path, *, desc: str = "") -> bool:
    """Download a URL to a local file. Returns True on success."""
    label = desc or url.split("/")[-1]
    print(f"    Downloading {label}...", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TermTube-Bootstrap/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            dest.parent.mkdir(parents=True, exist_ok=True)
            downloaded = 0
            with open(dest, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        print(f"\r    Downloading {label}... {pct}%", end="", flush=True)
            print(f"\r    Downloading {label}... done ({downloaded // 1024 // 1024}MB)", flush=True)
        return True
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"\n    [!] Download failed: {exc}", flush=True)
        dest.unlink(missing_ok=True)
        return False


def _make_executable(path: Path) -> None:
    """chmod +x on Unix, no-op on Windows."""
    if OS_NAME != "windows":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _github_latest_tag(owner: str, repo: str) -> str | None:
    """Fetch the latest release tag from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TermTube-Bootstrap/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("tag_name")
    except Exception:
        return None


# ── Tool Installers ───────────────────────────────────────────────────────────

def _install_ytdlp(bin_dir: Path) -> str | None:
    """Install yt-dlp nightly binary. Returns version string or None."""
    base_url = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download"
    if OS_NAME == "macos":
        asset = "yt-dlp_macos"
        dest_name = "yt-dlp"
    elif OS_NAME == "linux":
        asset = "yt-dlp"
        dest_name = "yt-dlp"
    else:
        asset = "yt-dlp.exe"
        dest_name = "yt-dlp.exe"

    dest = bin_dir / dest_name
    url = f"{base_url}/{asset}"

    if not _download(url, dest, desc="yt-dlp (nightly)"):
        return None

    _make_executable(dest)
    return "nightly-latest"


def _install_deno(bin_dir: Path) -> str | None:
    """Install Deno from GitHub releases. Returns version string or None."""
    tag = _github_latest_tag("denoland", "deno")
    if not tag:
        print("    [!] Could not determine latest Deno version", flush=True)
        return None

    if OS_NAME == "macos":
        if ARCH == "aarch64":
            asset = "deno-aarch64-apple-darwin.zip"
        else:
            asset = "deno-x86_64-apple-darwin.zip"
    elif OS_NAME == "linux":
        if ARCH == "aarch64":
            asset = "deno-aarch64-unknown-linux-gnu.zip"
        else:
            asset = "deno-x86_64-unknown-linux-gnu.zip"
    else:
        asset = "deno-x86_64-pc-windows-msvc.zip"

    url = f"https://github.com/denoland/deno/releases/download/{tag}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_deno_") as tmp:
        zip_path = Path(tmp) / asset
        if not _download(url, zip_path, desc=f"Deno {tag}"):
            return None

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)

        exe_name = "deno.exe" if OS_NAME == "windows" else "deno"
        src = Path(tmp) / exe_name
        if not src.exists():
            print(f"    [!] {exe_name} not found in archive", flush=True)
            return None

        dest = bin_dir / exe_name
        shutil.move(str(src), str(dest))
        _make_executable(dest)

    return tag


def _install_ffmpeg(bin_dir: Path) -> str | None:
    """Install ffmpeg + ffprobe from BtbN static builds. Returns version or None."""
    base_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"

    if OS_NAME == "macos":
        # BtbN doesn't provide macOS builds; use evermeet.cx
        return _install_ffmpeg_macos(bin_dir)
    elif OS_NAME == "linux":
        if ARCH == "aarch64":
            asset = "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
        else:
            asset = "ffmpeg-master-latest-linux64-gpl.tar.xz"
    else:
        asset = "ffmpeg-master-latest-win64-gpl.zip"

    url = f"{base_url}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_ffmpeg_") as tmp:
        archive_path = Path(tmp) / asset
        if not _download(url, archive_path, desc="ffmpeg (static)"):
            return None

        if asset.endswith(".tar.xz"):
            with tarfile.open(archive_path, "r:xz") as tf:
                tf.extractall(tmp)
        else:
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(tmp)

        # Find ffmpeg/ffprobe in extracted directory
        tmp_path = Path(tmp)
        for exe_name in ("ffmpeg", "ffprobe"):
            if OS_NAME == "windows":
                exe_name += ".exe"
            found = list(tmp_path.rglob(f"bin/{exe_name}"))
            if not found:
                found = list(tmp_path.rglob(exe_name))
            if found:
                dest = bin_dir / exe_name
                shutil.move(str(found[0]), str(dest))
                _make_executable(dest)
            else:
                print(f"    [!] {exe_name} not found in archive", flush=True)

    return "master-latest"


def _install_ffmpeg_macos(bin_dir: Path) -> str | None:
    """Install ffmpeg on macOS from evermeet.cx static builds."""
    for tool in ("ffmpeg", "ffprobe"):
        url = f"https://evermeet.cx/ffmpeg/get/{tool}/zip"
        with tempfile.TemporaryDirectory(prefix=f"termtube_{tool}_") as tmp:
            zip_path = Path(tmp) / f"{tool}.zip"
            if not _download(url, zip_path, desc=f"{tool} (macOS)"):
                return None
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            src = Path(tmp) / tool
            if not src.exists():
                print(f"    [!] {tool} not found in archive", flush=True)
                return None
            dest = bin_dir / tool
            shutil.move(str(src), str(dest))
            _make_executable(dest)
    return "evermeet-latest"


def _install_mpv(bin_dir: Path) -> str | None:
    """Install mpv from official releases. Returns version or None."""
    tag = _github_latest_tag("mpv-player", "mpv")
    if not tag:
        print("    [!] Could not determine latest mpv version", flush=True)
        return None

    if OS_NAME == "macos":
        if ARCH == "aarch64":
            # Try macOS 15 arm first, then 14
            asset = f"mpv-{tag}-macos-15-arm.zip"
        else:
            asset = f"mpv-{tag}-macos-15-intel.zip"
    elif OS_NAME == "windows":
        if ARCH == "aarch64":
            asset = f"mpv-{tag}-aarch64-pc-windows-msvc.zip"
        else:
            asset = f"mpv-{tag}-x86_64-pc-windows-msvc.zip"
    else:
        # Linux: official mpv doesn't ship static binaries.
        # Skip installation; user must have mpv from their package manager.
        print("    mpv: Linux users should install via package manager (apt/dnf/pacman).", flush=True)
        print("    Skipping mpv download for Linux.", flush=True)
        return "system"

    url = f"https://github.com/mpv-player/mpv/releases/download/{tag}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_mpv_") as tmp:
        zip_path = Path(tmp) / asset
        if not _download(url, zip_path, desc=f"mpv {tag}"):
            return None

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)

        if OS_NAME == "macos":
            # macOS zip contains mpv.app bundle; the binary is inside
            app_path = list(Path(tmp).rglob("mpv"))
            # Filter for the actual binary (not directory)
            binary = None
            for p in app_path:
                if p.is_file() and not p.suffix:
                    binary = p
                    break
            if binary is None:
                # Try inside .app bundle
                for p in Path(tmp).rglob("MacOS/mpv"):
                    if p.is_file():
                        binary = p
                        break
            if binary is None:
                print("    [!] mpv binary not found in archive", flush=True)
                return None
            dest = bin_dir / "mpv"
            shutil.move(str(binary), str(dest))
            _make_executable(dest)
        else:
            # Windows
            exe_name = "mpv.exe"
            found = list(Path(tmp).rglob(exe_name))
            if not found:
                print(f"    [!] {exe_name} not found in archive", flush=True)
                return None
            dest = bin_dir / exe_name
            shutil.move(str(found[0]), str(dest))

    return tag


# ── Public API ────────────────────────────────────────────────────────────────

TOOLS = {
    "yt-dlp": _install_ytdlp,
    "deno": _install_deno,
    "ffmpeg": _install_ffmpeg,
    "mpv": _install_mpv,
}


def is_tool_installed(name: str) -> bool:
    """Check if a tool is available in the deps bin dir."""
    bin_dir = get_deps_bin()
    exe_name = f"{name}.exe" if OS_NAME == "windows" else name
    # yt-dlp special case for Windows
    if name == "yt-dlp" and OS_NAME == "windows":
        exe_name = "yt-dlp.exe"
    if name == "ffmpeg":
        return (bin_dir / exe_name).exists()
    return (bin_dir / exe_name).exists()


def install_tool(name: str, *, force: bool = False) -> bool:
    """Install a single tool. Returns True on success.

    If force=True, re-downloads even if already present.
    """
    if name not in TOOLS:
        print(f"    [!] Unknown tool: {name}", flush=True)
        return False

    bin_dir = get_deps_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)

    if not force and is_tool_installed(name):
        return True

    installer = TOOLS[name]
    version = installer(bin_dir)

    if version:
        versions = _read_versions()
        versions[name] = {"version": version, "platform": f"{OS_NAME}-{ARCH}"}
        _write_versions(versions)
        return True

    return False


def install_all(*, force: bool = False) -> bool:
    """Install all dependencies. Returns True if all succeeded."""
    print("\n  Installing TermTube dependencies...", flush=True)
    print(f"  Platform: {OS_NAME} ({ARCH})", flush=True)
    print(f"  Install path: {get_deps_bin()}\n", flush=True)

    bin_dir = get_deps_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for name, installer in TOOLS.items():
        if not force and is_tool_installed(name):
            print(f"  [ok] {name} already installed", flush=True)
            continue

        print(f"  Installing {name}...", flush=True)
        version = installer(bin_dir)

        if version:
            versions = _read_versions()
            versions[name] = {"version": version, "platform": f"{OS_NAME}-{ARCH}"}
            _write_versions(versions)
            print(f"  [ok] {name} installed ({version})", flush=True)
        else:
            print(f"  [!!] {name} installation failed", flush=True)
            all_ok = False

    print(flush=True)
    if all_ok:
        print("  All dependencies installed successfully.", flush=True)
    else:
        print("  Some dependencies failed to install.", flush=True)
        print("  TermTube may not work correctly without them.", flush=True)

    return all_ok


def check_all() -> dict[str, bool]:
    """Check which tools are installed in the deps bin. Returns {tool: installed}."""
    return {name: is_tool_installed(name) for name in TOOLS}


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    force = "--force" in sys.argv
    success = install_all(force=force)
    sys.exit(0 if success else 1)
