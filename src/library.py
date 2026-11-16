"""Library page data: scans the download dirs for yt-dlp `.info.json` sidecars."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

from src.entries import LibraryEntry

_cache: dict[tuple[str, str], tuple[float, float, list[LibraryEntry]]] = {}
_lock = threading.Lock()
_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov")
_NON_MEDIA_EXTS = (".json", ".jpg", ".png", ".webp")


def _dir_mtime(directory: Path) -> float:
    try:
        return directory.stat().st_mtime if directory.exists() else 0.0
    except OSError:
        return 0.0


def _load_sidecar(info_path: Path, media_files: dict[str, Path]) -> LibraryEntry | None:
    try:
        data = json.loads(info_path.read_text())
        media_stem = info_path.stem.removesuffix(".info")
        media = media_files.get(media_stem)
        if media:
            data["_local_path"] = str(media)
            data["_local_type"] = "video" if media.suffix in _VIDEO_EXTS else "audio"
        data["_sidecar_path"] = str(info_path)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _scan_dir(directory: Path, media_type: str) -> Iterator[LibraryEntry]:
    if not directory.exists():
        return
    media_files: dict[str, Path] = {}
    info_files: list[Path] = []
    try:
        for f in directory.rglob("*"):
            if not f.is_file():
                continue
            if f.name.endswith(".info.json"):
                info_files.append(f)
            elif f.suffix not in _NON_MEDIA_EXTS:
                media_files[f.stem] = f
    except OSError:
        pass
    for info_path in info_files:
        entry = _load_sidecar(info_path, media_files)
        if entry:
            entry.setdefault("_local_type", media_type)
            yield entry


def all_entries(video_dir: Path, audio_dir: Path) -> list[LibraryEntry]:
    """Return library entries (video and audio merged by id), newest upload first.

    Cached until a directory mtime changes or `invalidate_cache()` is called.
    """
    with _lock:
        cache_key = (str(video_dir), str(audio_dir))
        cur_v_mtime = _dir_mtime(video_dir)
        cur_a_mtime = _dir_mtime(audio_dir)

        cached = _cache.get(cache_key)
        if cached is not None:
            cached_v_mtime, cached_a_mtime, cached_entries = cached
            if cached_v_mtime == cur_v_mtime and cached_a_mtime == cur_a_mtime:
                return cached_entries

        seen_ids: set[str] = set()
        entries: list[LibraryEntry] = []

        for entry in _scan_dir(video_dir, "video"):
            vid = entry.get("id", "")
            if vid not in seen_ids:
                seen_ids.add(vid)
                entries.append(entry)

        entries_by_id: dict[str, LibraryEntry] = {e.get("id", ""): e for e in entries if e.get("id")}
        for entry in _scan_dir(audio_dir, "audio"):
            vid = entry.get("id", "")
            if vid not in seen_ids:
                seen_ids.add(vid)
                entries.append(entry)
            else:
                existing = entries_by_id.get(vid)
                if existing is not None:
                    existing["_has_audio"] = True
                    existing["_audio_path"] = entry.get("_local_path")

        entries.sort(key=lambda e: e.get("upload_date", "0"), reverse=True)

        _cache[cache_key] = (cur_v_mtime, cur_a_mtime, entries)
        return entries


def invalidate_cache() -> None:
    """Force a rescan on next all_entries() call (e.g. after a download completes)."""
    with _lock:
        _cache.clear()
