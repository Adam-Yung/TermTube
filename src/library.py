"""Local library — videos/audio downloaded to disk via this TUI.

Each downloaded file has a .info.json sidecar written by yt-dlp
(--write-info-json flag). We scan both video_dir and audio_dir for
these sidecars to populate the Library page.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Iterator


def _load_sidecar(info_path: Path) -> dict | None:
    try:
        data = json.loads(info_path.read_text())
        # Attach the path of the actual media file (same stem, different ext)
        stem = info_path.stem  # e.g. "Title_Channel.info"
        # yt-dlp names sidecars as <title>.info.json — strip ".info"
        media_stem = stem.removesuffix(".info") if stem.endswith(".info") else stem
        # Look for a media file alongside the sidecar
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
    for info_path in directory.glob("**/*.info.json"):
        entry = _load_sidecar(info_path)
        if entry:
            entry.setdefault("_local_type", media_type)
            yield entry


def all_entries(video_dir: Path, audio_dir: Path) -> list[dict]:
    """Return all library entries (video + audio), sorted newest first."""
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
    return entries


def find_local(video_id: str, video_dir: Path, audio_dir: Path) -> dict:
    """Return dict with 'video_path' and/or 'audio_path' if saved locally."""
    result: dict = {}
    for d, key in [(video_dir, "video_path"), (audio_dir, "audio_path")]:
        if not d.exists():
            continue
        for info_path in d.glob(f"**/*.info.json"):
            try:
                data = json.loads(info_path.read_text())
                if data.get("id") == video_id:
                    sidecar = _load_sidecar(info_path)
                    if sidecar and sidecar.get("_local_path"):
                        result[key] = sidecar["_local_path"]
                    break
            except (json.JSONDecodeError, OSError):
                continue
    return result
