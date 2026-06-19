"""Dependency bootstrap — download and install binary dependencies from GitHub.

Only uses Python stdlib (urllib, zipfile, tarfile, json) so it can run
immediately after creating the venv, without any pip packages.

Install location: ~/.local/termtube-deps/bin/ (Unix) or %LOCALAPPDATA%\\termtube-deps\\bin\\ (Windows)

All 4 tools (yt-dlp, deno, ffmpeg, mpv) are required for full functionality:
  - yt-dlp: video/audio metadata extraction and stream URL resolution
  - deno: JavaScript runtime required by yt-dlp for YouTube challenges
  - ffmpeg: audio/video muxing and format conversion (required for downloads)
  - mpv: media playback via IPC
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


# ── Platform Detection ────────────────────────────────────────────────────────

def _detect_platform() -> tuple[str, str]:
    """Return (os_name, arch) normalized for download URL construction."""
    import platform as _platform
    os_name = sys.platform
    if os_name == "darwin":
        os_name = "macos"
    elif os_name.startswith("linux"):
        os_name = "linux"
    elif os_name == "win32":
        os_name = "windows"

    # platform.machine() returns the CPU architecture without spawning a subprocess.
    machine = _platform.machine().lower()
    if sys.platform == "win32":
        proc_arch = os.environ.get("PROCESSOR_ARCHITECTURE", "").lower()
        if proc_arch == "amd64":
            machine = "x86_64"

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

_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds


def _download(url: str, dest: Path, *, desc: str = "", retries: int = _MAX_RETRIES) -> bool:
    """Download a URL to a local file with retry logic. Returns True on success."""
    label = desc or url.split("/")[-1]

    for attempt in range(1, retries + 1):
        if attempt > 1:
            print(f"    Retry {attempt}/{retries}...", flush=True)
            time.sleep(_RETRY_DELAY * attempt)

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
                        if total > 0 and sys.stdout.isatty():
                            pct = downloaded * 100 // total
                            print(f"\r    Downloading {label}... {pct}%", end="", flush=True)
                if sys.stdout.isatty():
                    print(f"\r    Downloading {label}... done ({downloaded // 1024 // 1024}MB)", flush=True)
                else:
                    print(f"    Downloaded {label} ({downloaded // 1024 // 1024}MB)", flush=True)
            return True
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            print(f"\n    [!] Download failed: {exc}", flush=True)
            dest.unlink(missing_ok=True)
            if attempt == retries:
                return False

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
        if ARCH == "aarch64":
            asset = "deno-aarch64-pc-windows-msvc.zip"
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
    """Install ffmpeg + ffprobe static builds. Returns version or None.

    Sources:
      - Linux/Windows: BtbN/FFmpeg-Builds (GitHub, always available)
      - macOS: evermeet.cx static builds (with retry)
    """
    if OS_NAME == "macos":
        return _install_ffmpeg_macos(bin_dir)

    base_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"

    if OS_NAME == "linux":
        if ARCH == "aarch64":
            asset = "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
        else:
            asset = "ffmpeg-master-latest-linux64-gpl.tar.xz"
    else:
        if ARCH == "aarch64":
            asset = "ffmpeg-master-latest-winarm64-gpl.zip"
        else:
            asset = "ffmpeg-master-latest-win64-gpl.zip"

    url = f"{base_url}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_ffmpeg_") as tmp:
        archive_path = Path(tmp) / asset
        if not _download(url, archive_path, desc="ffmpeg (static)"):
            return None

        if asset.endswith(".tar.xz"):
            try:
                with tarfile.open(archive_path, "r:xz") as tf:
                    tf.extractall(tmp, filter="data" if hasattr(tarfile, "data_filter") else None)
            except tarfile.CompressionError:
                print("    [!] xz decompression not available (missing lzma module).", flush=True)
                print("    On Ubuntu/Debian: sudo apt install python3-lzma (or liblzma-dev + rebuild Python)", flush=True)
                return None
        else:
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(tmp)

        tmp_path = Path(tmp)
        installed_count = 0
        for base_name in ("ffmpeg", "ffprobe"):
            exe_name = f"{base_name}.exe" if OS_NAME == "windows" else base_name
            found = list(tmp_path.rglob(f"bin/{exe_name}"))
            if not found:
                found = list(tmp_path.rglob(exe_name))
            if found:
                dest = bin_dir / exe_name
                shutil.move(str(found[0]), str(dest))
                _make_executable(dest)
                installed_count += 1
            else:
                print(f"    [!] {exe_name} not found in archive", flush=True)

        if installed_count == 0:
            return None

    return "master-latest"


def _install_ffmpeg_macos(bin_dir: Path) -> str | None:
    """Install ffmpeg on macOS from eugeneware/ffmpeg-static GitHub releases.

    Uses .gz compressed binaries from GitHub (reliable, always available).
    Falls back to evermeet.cx if GitHub source fails.
    """
    import gzip

    tag = _github_latest_tag("eugeneware", "ffmpeg-static")
    if not tag:
        tag = "b6.1.1"  # known working fallback

    arch_suffix = "darwin-arm64" if ARCH == "aarch64" else "darwin-x64"

    for tool in ("ffmpeg", "ffprobe"):
        asset = f"{tool}-{arch_suffix}.gz"
        url = f"https://github.com/eugeneware/ffmpeg-static/releases/download/{tag}/{asset}"

        with tempfile.TemporaryDirectory(prefix=f"termtube_{tool}_") as tmp:
            gz_path = Path(tmp) / asset
            if not _download(url, gz_path, desc=f"{tool} (macOS {arch_suffix})"):
                # Fall back to evermeet.cx
                return _install_ffmpeg_macos_evermeet(bin_dir)

            dest = bin_dir / tool
            try:
                with gzip.open(gz_path, "rb") as gz_in:
                    with open(dest, "wb") as f_out:
                        shutil.copyfileobj(gz_in, f_out)
            except Exception as exc:
                print(f"    [!] Failed to decompress {tool}: {exc}", flush=True)
                dest.unlink(missing_ok=True)
                return None
            _make_executable(dest)

    return tag


def _install_ffmpeg_macos_evermeet(bin_dir: Path) -> str | None:
    """Fallback: install ffmpeg on macOS from evermeet.cx."""
    for tool in ("ffmpeg", "ffprobe"):
        url = f"https://evermeet.cx/ffmpeg/get/{tool}/zip"
        with tempfile.TemporaryDirectory(prefix=f"termtube_{tool}_") as tmp:
            zip_path = Path(tmp) / f"{tool}.zip"
            if not _download(url, zip_path, desc=f"{tool} (evermeet.cx)"):
                print(f"    [!] All ffmpeg sources failed.", flush=True)
                print(f"    Install manually: brew install ffmpeg", flush=True)
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
    """Install mpv from official releases. Returns version or None.

    macOS: downloads .app bundle from mpv-player/mpv, extracts binary + lib/.
    Windows: downloads zip with mpv.exe from mpv-player/mpv MSVC builds.
    Linux: no static binary available; user must install via system package manager.
    """
    # Last-known-good version used as fallback when the GitHub API is rate-limited.
    _MPV_FALLBACK = "v0.39.0"

    if OS_NAME == "linux":
        if shutil.which("mpv"):
            return "system"
        print("    mpv: no static Linux build available.", flush=True)
        print("    Install via your package manager:", flush=True)
        print("      Ubuntu/Debian: sudo apt install mpv", flush=True)
        print("      Fedora:        sudo dnf install mpv", flush=True)
        print("      Arch:          sudo pacman -S mpv", flush=True)
        return None

    tag = _github_latest_tag("mpv-player", "mpv")
    if not tag:
        print(f"    [!] GitHub API unavailable — using fallback mpv {_MPV_FALLBACK}", flush=True)
        tag = _MPV_FALLBACK

    if OS_NAME == "macos":
        import platform as _plat
        mac_ver = _plat.mac_ver()[0]
        mac_major = int(mac_ver.split('.')[0]) if mac_ver else 15
        if ARCH == "aarch64":
            asset = f"mpv-{tag}-macos-{mac_major}-arm.zip"
        else:
            asset = f"mpv-{tag}-macos-{mac_major}-intel.zip"
    else:
        if ARCH == "aarch64":
            asset = f"mpv-{tag}-aarch64-pc-windows-msvc.zip"
        else:
            asset = f"mpv-{tag}-x86_64-pc-windows-msvc.zip"

    url = f"https://github.com/mpv-player/mpv/releases/download/{tag}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_mpv_") as tmp:
        zip_path = Path(tmp) / asset
        if not _download(url, zip_path, desc=f"mpv {tag}"):
            return None
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)

        if OS_NAME == "macos":
            # macOS zip contains mpv.tar.gz holding an .app bundle.
            # The binary at Contents/MacOS/mpv links to @executable_path/lib/
            # so we must keep both the binary and lib/ directory together.
            inner_tar = Path(tmp) / "mpv.tar.gz"
            if inner_tar.exists():
                with tarfile.open(inner_tar, "r:gz") as tf:
                    tf.extractall(tmp, filter="data" if hasattr(tarfile, "data_filter") else None)
            macos_dir = None
            for p in Path(tmp).rglob("MacOS"):
                if p.is_dir() and (p / "mpv").exists():
                    macos_dir = p
                    break
            if macos_dir is None:
                print("    [!] mpv binary not found in .app bundle", flush=True)
                return None
            dest = bin_dir / "mpv"
            shutil.copy2(str(macos_dir / "mpv"), str(dest))
            _make_executable(dest)
            # Copy lib/ alongside the binary for @executable_path/lib/ resolution
            src_lib = macos_dir / "lib"
            if src_lib.is_dir():
                dest_lib = bin_dir / "lib"
                if dest_lib.exists():
                    shutil.rmtree(str(dest_lib))
                shutil.copytree(str(src_lib), str(dest_lib))
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
    """Check if a tool is available in the TermTube-managed deps bin dir.

    Only checks our managed directory — system PATH versions are ignored to
    ensure we always have full control over binary versions and updates.
    """
    bin_dir = get_deps_bin()

    if name == "ffmpeg":
        exe = "ffmpeg.exe" if OS_NAME == "windows" else "ffmpeg"
    elif name == "yt-dlp":
        exe = "yt-dlp.exe" if OS_NAME == "windows" else "yt-dlp"
    elif name == "deno":
        exe = "deno.exe" if OS_NAME == "windows" else "deno"
    elif name == "mpv":
        exe = "mpv.exe" if OS_NAME == "windows" else "mpv"
    else:
        exe = f"{name}.exe" if OS_NAME == "windows" else name

    return (bin_dir / exe).exists()


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
        print("  Run 'termtube --update' to retry.", flush=True)

    return all_ok


def check_all() -> dict[str, bool]:
    """Check which tools are installed in the deps bin or system PATH."""
    return {name: is_tool_installed(name) for name in TOOLS}


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    force = "--force" in sys.argv
    success = install_all(force=force)
    sys.exit(0 if success else 1)
