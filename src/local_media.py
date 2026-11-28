"""Details and thumbnails of local media files, read with the managed ffprobe and ffmpeg (never a PATH copy)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

from src import logger
from src.entries import Entry
from src.local_files import clean
from src.plat import IS_WINDOWS, get_deps_bin, get_popen_kwargs
from src.strings import text

_PROBE_TIMEOUT_S = 10
_FRAME_TIMEOUT_S = 15
_FRAME_AT_S = 3.0
_CACHE_MAX = 256
_TAGS = (("title", "tag_title"), ("artist", "tag_artist"), ("album", "tag_album"), ("date", "tag_date"),
         ("genre", "tag_genre"))

_cache: OrderedDict[str, dict] = OrderedDict()
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _tool(name: str) -> str | None:
    path = get_deps_bin() / (f"{name}.exe" if IS_WINDOWS else name)
    return str(path) if path.exists() else None


def _as_input(path: str) -> str:
    """`file:` keeps a name with a colon, a leading dash or a URL shape from being read as anything but a file."""
    return "file:" + path


def _run(cmd: list[str], timeout: float) -> bytes | None:
    try:
        done = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=False, **get_popen_kwargs(headless=True))
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("local media: %s failed: %s", os.path.basename(cmd[0]), exc)
        return None
    return done.stdout if done.returncode == 0 else None


def _probe(path: str) -> dict | None:
    exe = _tool("ffprobe")
    if not exe:
        return None
    out = _run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", _as_input(path)],
               _PROBE_TIMEOUT_S)
    try:
        return json.loads(out) if out else None
    except ValueError:
        return None


def _probed(entry: Entry) -> dict | None:
    """ffprobe's answer for a file row, cached by its id (which changes with the file's size and mtime)."""
    vid = entry.get("id", "")
    with _lock:
        if vid in _cache:
            _cache.move_to_end(vid)
            return _cache[vid]
    found = _probe(entry.get("_local_path", ""))
    if found is not None:
        with _lock:
            _cache[vid] = found
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
    return found


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fps(rate: str) -> str:
    num, _, den = (rate or "").partition("/")
    value = _number(num) / _number(den) if _number(den) else 0.0
    return f"{value:.3g} fps" if value else ""


def _stream_line(stream: dict) -> str:
    if stream.get("codec_type") == "video":
        size = f"{stream['width']}×{stream['height']}" if stream.get("width") else ""
        parts = [stream.get("codec_name", ""), size, _fps(stream.get("avg_frame_rate", ""))]
        return text("local_media.video_line", parts=" · ".join(p for p in parts if p))
    rate = _number(stream.get("sample_rate"))
    parts = [stream.get("codec_name", ""), f"{stream['channels']} ch" if stream.get("channels") else "",
             f"{rate / 1000:g} kHz" if rate else ""]
    return text("local_media.audio_line", parts=" · ".join(p for p in parts if p))


def _description(info: dict) -> str:
    fmt = info.get("format") or {}
    streams = [s for s in info.get("streams") or [] if s.get("codec_type") in ("video", "audio") and not _is_cover(s)]
    lines = [_stream_line(s) for s in streams]
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    lines += [text(f"local_media.{key}", value=tags[tag]) for tag, key in _TAGS if tags.get(tag)]
    if bitrate := _number(fmt.get("bit_rate")):
        lines.append(text("local_media.bitrate", value=f"{bitrate / 1e6:.2g}"))
    return "\n".join(clean(line) for line in lines) or text("local_media.unreadable")


def details(entry: Entry) -> dict:
    """Fields to merge into a file row: its length and a description of its streams and tags."""
    if not _tool("ffprobe"):
        return {"description": text("local_media.no_ffprobe")}
    info = _probed(entry)
    if not info:
        return {"description": text("local_media.unreadable")}
    duration = _number((info.get("format") or {}).get("duration"))
    fields: dict = {"description": _description(info)}
    if duration:
        fields["duration"] = int(duration)
    return fields


def _is_cover(stream: dict) -> bool:
    return bool((stream.get("disposition") or {}).get("attached_pic"))


def _frame_args(info: dict) -> list[str] | None:
    """ffmpeg input options picking the image: embedded cover art, else a frame at 3 s (mid-way in a shorter file)."""
    streams = info.get("streams") or []
    cover = next((s for s in streams if _is_cover(s)), None)
    if cover is not None:
        return ["-map", f"0:{cover.get('index', 0)}"]
    if not any(s.get("codec_type") == "video" for s in streams):
        return None
    duration = _number((info.get("format") or {}).get("duration"))
    at = _FRAME_AT_S if duration > _FRAME_AT_S else duration / 2
    return ["-ss", f"{at:g}", "-map", "0:v:0"]


def thumbnail(entry: Entry, dest: Path) -> Path | None:
    """Write a JPEG of the file row to ``dest`` and return it; None for audio without art, or without ffmpeg."""
    exe = _tool("ffmpeg")
    info = _probed(entry) if exe else None
    picked = _frame_args(info) if info else None
    if not picked:
        return None
    seek = picked[:2] if picked[0] == "-ss" else []
    tmp = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    cmd = [exe, "-nostdin", "-v", "error", "-y", *seek, "-i", _as_input(entry.get("_local_path", "")),
           *picked[len(seek):], "-frames:v", "1", "-vf", "scale=480:-2", "-f", "image2", "-c:v", "mjpeg",
           _as_input(str(tmp))]
    if _run(cmd, _FRAME_TIMEOUT_S) is None or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, dest)
    return dest
