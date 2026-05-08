"""TermTube v2 — local library (downloaded videos/audio).

Scans video_dir and audio_dir for *.info.json sidecars written by yt-dlp.
Returns a deduplicated list of entries sorted by upload_date descending.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


def _scan_dir(directory: Path, media_key: str) -> dict[str, dict]:
    """Return {video_id: entry} for all *.info.json files in directory."""
    entries: dict[str, dict] = {}
    if not directory.exists():
        return entries
    for info_file in sorted(directory.glob("*.info.json"), reverse=True):
        try:
            entry = json.loads(info_file.read_bytes())
            vid = entry.get("id")
            if not vid:
                continue
            # Find the actual media file alongside the .info.json
            stem = info_file.stem.replace(".info", "")
            for ext in ("mp4", "mkv", "webm", "mp3", "m4a", "opus", "ogg"):
                media_file = info_file.with_name(f"{stem}.{ext}")
                if media_file.exists():
                    entry[media_key] = str(media_file)
                    break
            if media_key in entry:
                entries[vid] = entry
        except Exception:
            continue
    return entries


def all_entries(video_dir: Path, audio_dir: Path) -> list[dict]:
    """Return all locally downloaded videos + audio, deduped, sorted by date."""
    videos = _scan_dir(video_dir, "_video_path")
    audios = _scan_dir(audio_dir, "_audio_path")

    merged: dict[str, dict] = {}
    for vid, entry in videos.items():
        merged[vid] = dict(entry)
        merged[vid]["_has_video"] = True
    for vid, entry in audios.items():
        if vid in merged:
            merged[vid]["_audio_path"] = entry.get("_audio_path")
            merged[vid]["_has_audio"] = True
        else:
            e = dict(entry)
            e["_has_audio"] = True
            merged[vid] = e

    def _sort_key(e: dict) -> str:
        return str(e.get("upload_date") or "0")

    return sorted(merged.values(), key=_sort_key, reverse=True)


def find_local(video_id: str, video_dir: Path, audio_dir: Path) -> dict[str, str | None]:
    """Return {video_path, audio_path} for a given video ID, or None values."""
    result: dict[str, str | None] = {"video_path": None, "audio_path": None}
    for entry in _scan_dir(video_dir, "_video_path").values():
        if entry.get("id") == video_id:
            result["video_path"] = entry.get("_video_path")
            break
    for entry in _scan_dir(audio_dir, "_audio_path").values():
        if entry.get("id") == video_id:
            result["audio_path"] = entry.get("_audio_path")
            break
    return result
