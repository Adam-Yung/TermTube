"""Local library — videos/audio downloaded to disk via this TUI.

Each downloaded file has a .info.json sidecar written by yt-dlp
(--write-info-json flag). We scan both video_dir and audio_dir for
these sidecars to populate the Library page.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Iterator

# Module-level result cache keyed by (video_dir, audio_dir).
# Each value is (mtime_video, mtime_audio, entries).
# We compare directory mtime before returning cached results — on most
# filesystems a newly created/deleted file bumps the parent dir mtime,
# making this a cheap O(1) staleness check.
_cache: dict[tuple[str, str], tuple[float, float, list[dict]]] = {}


def _dir_mtime(directory: Path) -> float:
    try:
        return directory.stat().st_mtime if directory.exists() else 0.0
    except OSError:
        return 0.0


def _load_sidecar(info_path: Path, media_files: dict[str, Path] | None = None) -> dict | None:
    try:
        data = json.loads(info_path.read_text())
        stem = info_path.stem  # e.g. "Title_Channel.info"
        media_stem = stem.removesuffix(".info") if stem.endswith(".info") else stem
        if media_files is not None:
            media = media_files.get(media_stem)
            if media:
                data["_local_path"] = str(media)
                data["_local_type"] = "video" if media.suffix in (".mp4", ".mkv", ".webm", ".avi", ".mov") else "audio"
        else:
            for sibling in info_path.parent.iterdir():
                if sibling.stem == media_stem and sibling.suffix not in (".json", ".jpg", ".png", ".webp"):
                    data["_local_path"] = str(sibling)
                    data["_local_type"] = "video" if sibling.suffix in (".mp4", ".mkv", ".webm", ".avi", ".mov") else "audio"
                    break
        data["_sidecar_path"] = str(info_path)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _scan_dir(directory: Path, media_type: str) -> Iterator[dict]:
    if not directory.exists():
        return
    # Build a lookup of media files by stem for O(1) matching
    media_files: dict[str, Path] = {}
    try:
        for f in directory.iterdir():
            if f.suffix not in (".json", ".jpg", ".png", ".webp") and f.is_file():
                media_files[f.stem] = f
    except OSError:
        pass
    for info_path in directory.glob("**/*.info.json"):
        entry = _load_sidecar(info_path, media_files)
        if entry:
            entry.setdefault("_local_type", media_type)
            yield entry


def all_entries(video_dir: Path, audio_dir: Path) -> list[dict]:
    """Return all library entries (video + audio), sorted newest first.

    Results are cached in memory and invalidated when either directory's
    mtime changes (i.e. a file is added or removed).
    """
    cache_key = (str(video_dir), str(audio_dir))
    cur_v_mtime = _dir_mtime(video_dir)
    cur_a_mtime = _dir_mtime(audio_dir)

    cached = _cache.get(cache_key)
    if cached is not None:
        cached_v_mtime, cached_a_mtime, cached_entries = cached
        if cached_v_mtime == cur_v_mtime and cached_a_mtime == cur_a_mtime:
            return cached_entries

    seen_ids: set[str] = set()
    entries: list[dict] = []

    for entry in _scan_dir(video_dir, "video"):
        vid = entry.get("id", "")
        if vid not in seen_ids:
            seen_ids.add(vid)
            entries.append(entry)

    for entry in _scan_dir(audio_dir, "audio"):
        vid = entry.get("id", "")
        if vid not in seen_ids:
            seen_ids.add(vid)
            entries.append(entry)
        else:
            # Already have this video — mark it as having both
            for e in entries:
                if e.get("id") == vid:
                    e["_has_audio"] = True
                    e["_audio_path"] = entry.get("_local_path")
                    break

    # Sort by upload_date desc (yt-dlp uses YYYYMMDD strings)
    entries.sort(key=lambda e: e.get("upload_date", "0"), reverse=True)

    _cache[cache_key] = (cur_v_mtime, cur_a_mtime, entries)
    return entries


def invalidate_cache() -> None:
    """Force a rescan on next all_entries() call (e.g. after a download completes)."""
    _cache.clear()
