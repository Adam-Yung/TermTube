"""Installs the bundled tools (deno, ffmpeg, mpv) from GitHub releases. Stdlib only, so it runs before pip."""

from __future__ import annotations

import gzip
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from src.plat import get_deps_bin, get_deps_dir, is_tool_installed
from src.release_download import download, github_latest_tag


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

_MPV_FALLBACK = "v0.39.0"  # used when the GitHub API is rate-limited


def _versions_file() -> Path:
    return get_deps_dir() / "versions.json"


def _read_versions() -> dict:
    vf = _versions_file()
    if vf.exists():
        try:
            return json.loads(vf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_versions(data: dict) -> None:
    vf = _versions_file()
    vf.parent.mkdir(parents=True, exist_ok=True)
    vf.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_executable(path: Path) -> None:
    """chmod +x; no-op on Windows."""
    if OS_NAME != "windows":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _install_binary(source: Path, bin_dir: Path, name: str) -> None:
    dest = bin_dir / name
    shutil.move(str(source), str(dest))
    _make_executable(dest)


def _extract_tar(archive: Path, mode: str, into: str) -> None:
    with tarfile.open(archive, mode) as tf:
        tf.extractall(into, filter="data" if hasattr(tarfile, "data_filter") else None)


def _extract_zip(archive: Path, into: str) -> None:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(into)


def _install_deno(bin_dir: Path) -> str | None:
    """Install Deno from GitHub releases. Returns the tag or None."""
    tag = github_latest_tag("denoland", "deno")
    if not tag:
        print("    [!] Could not determine latest Deno version", flush=True)
        return None

    triple = {
        "macos": "apple-darwin",
        "linux": "unknown-linux-gnu",
        "windows": "pc-windows-msvc",
    }.get(OS_NAME, "pc-windows-msvc")
    asset = f"deno-{'aarch64' if ARCH == 'aarch64' else 'x86_64'}-{triple}.zip"

    url = f"https://github.com/denoland/deno/releases/download/{tag}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_deno_") as tmp:
        zip_path = Path(tmp) / asset
        if not download(url, zip_path, desc=f"Deno {tag}"):
            return None
        _extract_zip(zip_path, tmp)
        exe_name = "deno.exe" if OS_NAME == "windows" else "deno"
        src = Path(tmp) / exe_name
        if not src.exists():
            print(f"    [!] {exe_name} not found in archive", flush=True)
            return None
        _install_binary(src, bin_dir, exe_name)

    return tag


def _ffmpeg_asset() -> str:
    """The BtbN build for this Linux or Windows machine."""
    arm = ARCH == "aarch64"
    if OS_NAME == "linux":
        return f"ffmpeg-master-latest-{'linuxarm64' if arm else 'linux64'}-gpl.tar.xz"
    return f"ffmpeg-master-latest-{'winarm64' if arm else 'win64'}-gpl.zip"


def _extract_ffmpeg(archive: Path, into: str) -> bool:
    if not archive.name.endswith(".tar.xz"):
        _extract_zip(archive, into)
        return True
    try:
        _extract_tar(archive, "r:xz", into)
    except tarfile.CompressionError:
        print("    [!] xz decompression not available (missing lzma module).", flush=True)
        print("    On Ubuntu/Debian: sudo apt install python3-lzma (or liblzma-dev, then rebuild)", flush=True)
        return False
    return True


def _install_found(tree: Path, bin_dir: Path, base_name: str) -> bool:
    """Move ``base_name`` from the unpacked ``tree`` (preferably from a ``bin`` folder) into ``bin_dir``."""
    exe_name = f"{base_name}.exe" if OS_NAME == "windows" else base_name
    found = list(tree.rglob(f"bin/{exe_name}")) or list(tree.rglob(exe_name))
    if not found:
        print(f"    [!] {exe_name} not found in archive", flush=True)
        return False
    _install_binary(found[0], bin_dir, exe_name)
    return True


def _install_ffmpeg(bin_dir: Path) -> str | None:
    """Install ffmpeg + ffprobe static builds (BtbN on Linux/Windows). Returns a version label or None."""
    if OS_NAME == "macos":
        return _install_ffmpeg_macos(bin_dir)

    asset = _ffmpeg_asset()
    url = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_ffmpeg_") as tmp:
        archive_path = Path(tmp) / asset
        if not download(url, archive_path, desc="ffmpeg (static)"):
            return None
        if not _extract_ffmpeg(archive_path, tmp):
            return None
        installed = [_install_found(Path(tmp), bin_dir, name) for name in ("ffmpeg", "ffprobe")]
        if not any(installed):
            return None

    return "master-latest"


def _gunzip_binary(gz_path: Path, dest: Path) -> bool:
    try:
        with gzip.open(gz_path, "rb") as gz_in, open(dest, "wb") as f_out:
            shutil.copyfileobj(gz_in, f_out)
    except Exception as exc:
        print(f"    [!] Failed to decompress {dest.name}: {exc}", flush=True)
        dest.unlink(missing_ok=True)
        return False
    _make_executable(dest)
    return True


def _install_ffmpeg_macos(bin_dir: Path) -> str | None:
    """Install ffmpeg on macOS from eugeneware/ffmpeg-static .gz binaries; falls back to evermeet.cx."""
    tag = github_latest_tag("eugeneware", "ffmpeg-static") or "b6.1.1"
    arch_suffix = "darwin-arm64" if ARCH == "aarch64" else "darwin-x64"

    for tool in ("ffmpeg", "ffprobe"):
        asset = f"{tool}-{arch_suffix}.gz"
        url = f"https://github.com/eugeneware/ffmpeg-static/releases/download/{tag}/{asset}"

        with tempfile.TemporaryDirectory(prefix=f"termtube_{tool}_") as tmp:
            gz_path = Path(tmp) / asset
            if not download(url, gz_path, desc=f"{tool} (macOS {arch_suffix})"):
                return _install_ffmpeg_macos_evermeet(bin_dir)
            if not _gunzip_binary(gz_path, bin_dir / tool):
                return None

    return tag


def _install_ffmpeg_macos_evermeet(bin_dir: Path) -> str | None:
    """Fallback ffmpeg source for macOS."""
    for tool in ("ffmpeg", "ffprobe"):
        url = f"https://evermeet.cx/ffmpeg/get/{tool}/zip"
        with tempfile.TemporaryDirectory(prefix=f"termtube_{tool}_") as tmp:
            zip_path = Path(tmp) / f"{tool}.zip"
            if not download(url, zip_path, desc=f"{tool} (evermeet.cx)"):
                print("    [!] All ffmpeg sources failed.", flush=True)
                print("    Install manually: brew install ffmpeg", flush=True)
                return None
            _extract_zip(zip_path, tmp)
            src = Path(tmp) / tool
            if not src.exists():
                print(f"    [!] {tool} not found in archive", flush=True)
                return None
            _install_binary(src, bin_dir, tool)
    return "evermeet-latest"


def _link_system_mpv(bin_dir: Path, system_mpv: Path) -> str | None:
    """Link a distro-installed mpv into the managed bin dir, which is where the rest of the app looks for it.

    There is no static Linux build to download. Returns "system", or None if the link cannot be made.
    """
    link = bin_dir / "mpv"
    target = system_mpv.resolve()
    if target.parent == bin_dir.resolve():  # PATH already led to our own link
        return "system" if link.exists() else None
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        return "system"  # a real file the user placed there
    try:
        link.symlink_to(target)
    except OSError as exc:
        print(f"    mpv: could not link {target} into {bin_dir}: {exc}", flush=True)
        return None
    return "system"


def _use_system_mpv(bin_dir: Path) -> str | None:
    """Linux: link the distro's mpv, or print how to install one."""
    system = shutil.which("mpv")
    if system:
        return _link_system_mpv(bin_dir, Path(system))
    print("    mpv: no static Linux build available.", flush=True)
    print("    Install via your package manager:", flush=True)
    print("      Ubuntu/Debian: sudo apt install mpv", flush=True)
    print("      Fedora:        sudo dnf install mpv", flush=True)
    print("      Arch:          sudo pacman -S mpv", flush=True)
    return None


def _mpv_asset(tag: str) -> str:
    """The mpv release archive for this macOS or Windows machine."""
    if OS_NAME != "macos":
        return f"mpv-{tag}-{'aarch64' if ARCH == 'aarch64' else 'x86_64'}-pc-windows-msvc.zip"
    mac_ver = platform.mac_ver()[0]
    mac_major = int(mac_ver.split('.')[0]) if mac_ver else 15
    return f"mpv-{tag}-macos-{mac_major}-{'arm' if ARCH == 'aarch64' else 'intel'}.zip"


def _place_mpv_macos(tmp: str, bin_dir: Path) -> bool:
    """Copy mpv out of the unpacked .app. It links @executable_path/lib/, so bin/mpv and bin/lib stay together."""
    inner_tar = Path(tmp) / "mpv.tar.gz"
    if inner_tar.exists():
        _extract_tar(inner_tar, "r:gz", tmp)
    macos_dir = next((p for p in Path(tmp).rglob("MacOS") if p.is_dir() and (p / "mpv").exists()), None)
    if macos_dir is None:
        print("    [!] mpv binary not found in .app bundle", flush=True)
        return False
    dest = bin_dir / "mpv"
    shutil.copy2(str(macos_dir / "mpv"), str(dest))
    _make_executable(dest)
    src_lib = macos_dir / "lib"
    if src_lib.is_dir():
        dest_lib = bin_dir / "lib"
        if dest_lib.exists():
            shutil.rmtree(str(dest_lib))
        shutil.copytree(str(src_lib), str(dest_lib))
    return True


def _place_mpv_windows(tmp: str, bin_dir: Path) -> bool:
    found = list(Path(tmp).rglob("mpv.exe"))
    if not found:
        print("    [!] mpv.exe not found in archive", flush=True)
        return False
    shutil.move(str(found[0]), str(bin_dir / "mpv.exe"))
    return True


def _install_mpv(bin_dir: Path) -> str | None:
    """Install mpv (macOS .app bundle, Windows zip). Linux has no static build: accepts a system mpv."""
    if OS_NAME == "linux":
        return _use_system_mpv(bin_dir)

    tag = github_latest_tag("mpv-player", "mpv")
    if not tag:
        print(f"    [!] GitHub API unavailable — using fallback mpv {_MPV_FALLBACK}", flush=True)
        tag = _MPV_FALLBACK

    asset = _mpv_asset(tag)
    url = f"https://github.com/mpv-player/mpv/releases/download/{tag}/{asset}"

    with tempfile.TemporaryDirectory(prefix="termtube_mpv_") as tmp:
        zip_path = Path(tmp) / asset
        if not download(url, zip_path, desc=f"mpv {tag}"):
            return None
        _extract_zip(zip_path, tmp)
        place = _place_mpv_macos if OS_NAME == "macos" else _place_mpv_windows
        if not place(tmp, bin_dir):
            return None

    return tag


TOOLS = {
    "deno": _install_deno,
    "ffmpeg": _install_ffmpeg,
    "mpv": _install_mpv,
}


def _install_and_record(name: str, bin_dir: Path) -> str | None:
    version = TOOLS[name](bin_dir)
    if version:
        versions = _read_versions()
        versions[name] = {"version": version, "platform": f"{OS_NAME}-{ARCH}"}
        _write_versions(versions)
    return version


def install_tool(name: str, *, force: bool = False) -> bool:
    """Install one tool; skipped if present unless force. True on success."""
    if name not in TOOLS:
        print(f"    [!] Unknown tool: {name}", flush=True)
        return False

    bin_dir = get_deps_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)

    if not force and is_tool_installed(name):
        return True

    return _install_and_record(name, bin_dir) is not None


def install_all(*, force: bool = False) -> bool:
    """Install every tool in TOOLS. True if all succeeded."""
    print("\n  Installing TermTube dependencies...", flush=True)
    print(f"  Platform: {OS_NAME} ({ARCH})", flush=True)
    print(f"  Install path: {get_deps_bin()}\n", flush=True)

    bin_dir = get_deps_bin()
    bin_dir.mkdir(parents=True, exist_ok=True)

    all_ok = True
    for name in TOOLS:
        if not force and is_tool_installed(name):
            print(f"  [ok] {name} already installed", flush=True)
            continue

        print(f"  Installing {name}...", flush=True)
        version = _install_and_record(name, bin_dir)
        if version:
            print(f"  [ok] {name} installed ({version})", flush=True)
        else:
            print(f"  [!!] {name} installation failed", flush=True)
            all_ok = False

    print(flush=True)
    if all_ok:
        print("  All dependencies installed successfully.", flush=True)
    else:
        print("  Some dependencies failed to install.", file=sys.stderr, flush=True)
        print("  The app will still launch but some features may be unavailable.", file=sys.stderr, flush=True)
        print("  Run 'termtube --update' to retry downloads later.", file=sys.stderr, flush=True)

    return all_ok


if __name__ == "__main__":
    sys.exit(0 if install_all(force="--force" in sys.argv) else 1)
