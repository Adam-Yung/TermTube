"""The installers against fake release archives: which URL is fetched and what lands in the managed bin dir."""

import gzip
import io
import tarfile
import urllib.error
import zipfile

import pytest

from src import bootstrap, release_download


class Reply(io.BytesIO):
    def __init__(self, body, url=""):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}
        self._url = url

    def geturl(self):
        return self._url


def zipped(*names):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in names:
            zf.writestr(name, name)
    return out.getvalue()


def tarred(mode, *names):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode=mode) as tf:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = len(name)
            tf.addfile(info, io.BytesIO(name.encode()))
    return out.getvalue()


class Releases:
    """A fake network: the GitHub API names v9, downloads are answered from ``routes`` by part of the URL."""

    def __init__(self):
        self.asked, self.routes = [], {}

    def urlopen(self, req, timeout=None):
        url = req.full_url
        if "api.github.com" in url:
            return Reply(b'{"tag_name": "v9"}')
        self.asked.append(url)
        body = next((b for part, b in self.routes.items() if part in url), urllib.error.URLError("connection refused"))
        if isinstance(body, Exception):
            raise body
        return Reply(body)

    def __call__(self, routes):
        """Answer with ``routes``; returns the list of download URLs asked for."""
        self.routes = routes
        return self.asked


@pytest.fixture
def serve(monkeypatch):
    releases = Releases()
    monkeypatch.setattr("urllib.request.urlopen", releases.urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return releases


def target(monkeypatch, os_name, arch="x86_64"):
    monkeypatch.setattr(bootstrap, "OS_NAME", os_name)
    monkeypatch.setattr(bootstrap, "ARCH", arch)


def names(directory):
    return sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())


def test_deno_is_taken_from_the_zip(tmp_path, monkeypatch, serve):
    target(monkeypatch, "linux")
    asked = serve({"deno": zipped("deno")})
    assert bootstrap.TOOLS["deno"](tmp_path) == "v9"
    assert asked == ["https://github.com/denoland/deno/releases/download/v9/deno-x86_64-unknown-linux-gnu.zip"]
    assert names(tmp_path) == ["deno"]


def test_a_deno_zip_without_the_binary_fails(tmp_path, monkeypatch, serve, capsys):
    target(monkeypatch, "windows")
    serve({"deno": zipped("readme")})
    assert bootstrap.TOOLS["deno"](tmp_path) is None
    assert "deno.exe not found in archive" in capsys.readouterr().out


def test_ffmpeg_on_linux_comes_from_the_tar(tmp_path, monkeypatch, serve):
    target(monkeypatch, "linux", "aarch64")
    asked = serve({"BtbN": tarred("w:xz", "x/bin/ffmpeg", "x/bin/ffprobe")})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) == "master-latest"
    assert asked[0].endswith("/ffmpeg-master-latest-linuxarm64-gpl.tar.xz")
    assert names(tmp_path) == ["ffmpeg", "ffprobe"]


def test_ffmpeg_on_windows_keeps_what_it_finds(tmp_path, monkeypatch, serve, capsys):
    target(monkeypatch, "windows")
    serve({"BtbN": zipped("x/ffmpeg.exe")})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) == "master-latest"
    assert names(tmp_path) == ["ffmpeg.exe"]
    assert "ffprobe.exe not found in archive" in capsys.readouterr().out


def test_ffmpeg_with_neither_binary_fails(tmp_path, monkeypatch, serve):
    target(monkeypatch, "windows")
    serve({"BtbN": zipped("readme")})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) is None


def test_ffmpeg_on_macos_is_gunzipped(tmp_path, monkeypatch, serve):
    target(monkeypatch, "macos", "aarch64")
    asked = serve({"eugeneware": gzip.compress(b"bin")})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) == "v9"
    assert [u.rsplit("/", 1)[-1] for u in asked] == ["ffmpeg-darwin-arm64.gz", "ffprobe-darwin-arm64.gz"]
    assert (tmp_path / "ffprobe").read_bytes() == b"bin"


def test_a_corrupt_macos_ffmpeg_leaves_nothing(tmp_path, monkeypatch, serve, capsys):
    target(monkeypatch, "macos")
    serve({"eugeneware": b"not gzip"})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) is None
    assert names(tmp_path) == []
    assert "Failed to decompress ffmpeg" in capsys.readouterr().out


def test_ffmpeg_on_macos_falls_back_to_evermeet(tmp_path, monkeypatch, serve):
    target(monkeypatch, "macos")
    serve({"ffmpeg/zip": zipped("ffmpeg"), "ffprobe/zip": zipped("ffprobe")})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) == "evermeet-latest"
    assert names(tmp_path) == ["ffmpeg", "ffprobe"]


def test_when_every_ffmpeg_source_fails_the_manual_command_is_shown(tmp_path, monkeypatch, serve, capsys):
    target(monkeypatch, "macos")
    serve({})
    assert bootstrap.TOOLS["ffmpeg"](tmp_path) is None
    captured = capsys.readouterr()
    assert "All ffmpeg sources failed." in captured.out
    assert "Connection refused" in captured.out
    assert "Check your internet connection and firewall settings" in captured.err


@pytest.mark.parametrize("error,brief,advice", [
    (urllib.error.URLError("CERTIFICATE_VERIFY_FAILED"), "SSL/TLS error", "corporate proxy/firewall"),
    (urllib.error.URLError(TimeoutError("timed out")), "Connection timed out", "Disconnect from VPN/proxy"),
    (OSError("Connection reset by peer"), "Connection reset", "firewall settings"),
    (OSError("Network is unreachable"), "Network is unreachable", "firewall settings"),
    (OSError("disk full"), "disk full", "Check your internet connection"),
])
def test_download_failures_are_explained(tmp_path, monkeypatch, serve, capsys, error, brief, advice):
    target(monkeypatch, "linux")
    monkeypatch.setattr(release_download, "IS_MACOS", False)
    monkeypatch.setattr(release_download, "IS_LINUX", True)
    asked = serve({"deno": error})
    assert bootstrap.TOOLS["deno"](tmp_path) is None
    captured = capsys.readouterr()
    assert len(asked) == 3
    assert f"Download failed: {brief}" in captured.out
    assert advice in captured.err
    assert "apt install Deno v9" in captured.err


def test_mpv_on_macos_keeps_lib_next_to_the_binary(tmp_path, monkeypatch, serve):
    target(monkeypatch, "macos", "aarch64")
    monkeypatch.setattr("platform.mac_ver", lambda: ("15.1", ("", "", ""), ""))
    inner = tarred("w:gz", "mpv.app/Contents/MacOS/mpv", "mpv.app/Contents/MacOS/lib/a.dylib")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("mpv.tar.gz", inner)
    asked = serve({"mpv-player": out.getvalue()})
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "stale").write_text("x", encoding="utf-8")
    assert bootstrap.TOOLS["mpv"](tmp_path) == "v9"
    assert asked[0].endswith("/v9/mpv-v9-macos-15-arm.zip")
    assert names(tmp_path) == ["lib/a.dylib", "mpv"]


def test_a_macos_mpv_archive_without_the_binary_fails(tmp_path, monkeypatch, serve, capsys):
    target(monkeypatch, "macos")
    monkeypatch.setattr("platform.mac_ver", lambda: ("", ("", "", ""), ""))
    asked = serve({"mpv-player": zipped("readme")})
    assert bootstrap.TOOLS["mpv"](tmp_path) is None
    assert asked[0].endswith("/mpv-v9-macos-15-intel.zip")
    assert "mpv binary not found in .app bundle" in capsys.readouterr().out


def test_mpv_on_windows_is_found_anywhere_in_the_zip(tmp_path, monkeypatch, serve):
    target(monkeypatch, "windows")
    asked = serve({"mpv-player": zipped("dir/mpv.exe")})
    assert bootstrap.TOOLS["mpv"](tmp_path) == "v9"
    assert asked[0].endswith("/mpv-v9-x86_64-pc-windows-msvc.zip")
    assert names(tmp_path) == ["mpv.exe"]
