"""Reads the download dirs: finds `.info.json` sidecars and the files beside them, and builds Library entries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from src import logger
from src.entries import LibraryEntry
from src.history import slim

_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov")
MEDIA_EXTS = _VIDEO_EXTS + (".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".aac")
IMAGE_EXTS = (".jpg", ".png", ".webp")
_INDEX_KEYS = ("title", "uploader", "channel", "channel_id", "duration", "upload_date", "view_count",
               "webpage_url", "tags", "thumbnail")
_DESCRIPTION_MAX = 500
INFO = ".info.json"


def dir_mtime(directory: Path) -> float:
    """Newest mtime among ``directory`` and its subdirectories; a file added in any of them bumps one."""
    newest = 0.0
    pending = [str(directory)]
    while pending:
        current = pending.pop()
        try:
            newest = max(newest, os.stat(current).st_mtime)
            pending.extend(e.path for e in os.scandir(current) if e.is_dir(follow_symlinks=False))
        except OSError:
            continue
    return newest


@dataclass
class _Walk:
    """What one pass over a root found: sidecars as (path, mtime, size); media and thumbnails by (dir, stem)."""

    sidecars: list[tuple[str, float, int]] = field(default_factory=list)
    media: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    thumbs: dict[tuple[str, str], str] = field(default_factory=dict)


def _walk(root: Path) -> _Walk:
    """One `os.scandir` pass over ``root``; symlinks (files and folders) are never followed or listed."""
    found = _Walk()
    pending = [str(root)]
    while pending:
        current = pending.pop()
        try:
            children = list(os.scandir(current))
        except OSError:
            continue
        for child in children:
            _visit(found, pending, current, child)
    return found


def _visit(found: _Walk, pending: list[str], directory: str, child: os.DirEntry) -> None:
    """Queue a folder or record a file; anything unreadable is skipped."""
    try:
        if child.is_dir(follow_symlinks=False):
            pending.append(child.path)
        elif child.is_file(follow_symlinks=False):
            _sort_file(found, directory, child)
    except OSError:
        pass


def _sort_file(found: _Walk, directory: str, child: os.DirEntry) -> None:
    if child.name.endswith(INFO):
        st = child.stat(follow_symlinks=False)
        found.sidecars.append((child.path, st.st_mtime, st.st_size))
        return
    stem, ext = os.path.splitext(child.name)
    ext = ext.lower()
    key = (directory, stem)
    if ext in MEDIA_EXTS:
        found.media[key] = (child.path, child.stat(follow_symlinks=False).st_size)
    elif ext in IMAGE_EXTS and (ext == ".jpg" or key not in found.thumbs):
        found.thumbs[key] = child.path


def parse_sidecar(path: str, mtime: float, size: int) -> dict | None:
    """The index record for one sidecar, or None when it is unreadable or has no id."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        vid = data["id"]
    except (OSError, ValueError, KeyError, TypeError):
        logger.debug("library: skipped unreadable sidecar %s", path)
        return None
    entry = slim(data, vid, _INDEX_KEYS)
    entry["description"] = (data.get("description") or "")[:_DESCRIPTION_MAX]
    return {"mtime": mtime, "size": size, "entry": entry}


def scan_root(root: Path, kind: str, index: dict, fresh: dict) -> list[LibraryEntry]:
    """Entries for one root, reusing ``index`` records whose (mtime, size) still match; kept ones go to ``fresh``."""
    if not root.exists():
        return []
    found = _walk(root)
    entries: list[LibraryEntry] = []
    for path, mtime, size in found.sidecars:
        record = index.get(path)
        if not record or record["mtime"] != mtime or record["size"] != size:
            record = parse_sidecar(path, mtime, size)
            if record is None:
                continue
        fresh[path] = record
        key = (os.path.dirname(path), os.path.basename(path).removesuffix(INFO))
        entry: LibraryEntry = dict(record["entry"])
        entry["_sidecar_path"] = path
        entry["_local_type"] = kind
        media = found.media.get(key)
        if media:
            entry["_local_path"], entry["_size"] = media
        else:
            entry["_missing_file"] = True
        if key in found.thumbs:
            entry["_thumb_path"] = found.thumbs[key]
        entries.append(entry)
    return entries


def merge(video: list[LibraryEntry], audio: list[LibraryEntry]) -> list[LibraryEntry]:
    """Video entries plus audio-only ones; an audio file of a listed video id is folded into the video's row."""
    by_id = {e["id"]: e for e in video}
    for entry in audio:
        existing = by_id.get(entry["id"])
        if existing is None:
            by_id[entry["id"]] = entry
        elif existing.get("_missing_file") and not entry.get("_missing_file"):
            by_id[entry["id"]] = entry
        elif not entry.get("_missing_file"):
            existing["_has_audio"] = True
            existing["_audio_path"] = entry["_local_path"]
            existing["_audio_size"] = entry["_size"]
            existing["_audio_sidecar_path"] = entry["_sidecar_path"]
    return sorted(by_id.values(), key=lambda e: e.get("upload_date") or "0", reverse=True)
