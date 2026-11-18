"""Library page data: a slim, persisted index of the download dirs' yt-dlp `.info.json` sidecars, and file deletion."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from src import logger
from src.entries import LibraryEntry
from src.history import slim
from src.plat import get_cache_dir
from src.store import JsonStore

INDEX_PATH = get_cache_dir() / "library.json"

_VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov")
_MEDIA_EXTS = _VIDEO_EXTS + (".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".aac")
_IMAGE_EXTS = (".jpg", ".png", ".webp")
_SUBTITLE_EXTS = (".vtt", ".srt", ".ass", ".lrc")
_INDEX_KEYS = ("title", "uploader", "channel", "channel_id", "duration", "upload_date", "view_count",
               "webpage_url", "tags", "thumbnail")
_DESCRIPTION_MAX = 500
_INFO = ".info.json"

# {sidecar path: {"mtime", "size", "entry": slim record}}; only changed or new sidecars are parsed again.
_index = JsonStore(lambda: INDEX_PATH, version=1, default=dict)
_cache: dict[tuple[str, str], tuple[float, float, list[LibraryEntry]]] = {}
_lock = threading.Lock()


def _replace(data: dict, records: dict, keep: bool = False) -> bool:
    """Store callback: make the index ``records`` (or add them to what is there when ``keep``)."""
    if not keep:
        data.clear()
    data.update(records)
    return True


def _dir_mtime(directory: Path) -> float:
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
            try:
                if child.is_dir(follow_symlinks=False):
                    pending.append(child.path)
                elif child.is_file(follow_symlinks=False):
                    _sort_file(found, current, child)
            except OSError:
                continue
    return found


def _sort_file(found: _Walk, directory: str, child: os.DirEntry) -> None:
    if child.name.endswith(_INFO):
        st = child.stat(follow_symlinks=False)
        found.sidecars.append((child.path, st.st_mtime, st.st_size))
        return
    stem, ext = os.path.splitext(child.name)
    ext = ext.lower()
    key = (directory, stem)
    if ext in _MEDIA_EXTS:
        found.media[key] = (child.path, child.stat(follow_symlinks=False).st_size)
    elif ext in _IMAGE_EXTS and (ext == ".jpg" or key not in found.thumbs):
        found.thumbs[key] = child.path


def _parse(path: str, mtime: float, size: int) -> dict | None:
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


def _scan_root(root: Path, kind: str, index: dict, fresh: dict) -> list[LibraryEntry]:
    """Entries for one root, reusing ``index`` records whose (mtime, size) still match; kept ones go to ``fresh``."""
    if not root.exists():
        return []
    found = _walk(root)
    entries: list[LibraryEntry] = []
    for path, mtime, size in found.sidecars:
        record = index.get(path)
        if not record or record["mtime"] != mtime or record["size"] != size:
            record = _parse(path, mtime, size)
            if record is None:
                continue
        fresh[path] = record
        key = (os.path.dirname(path), os.path.basename(path).removesuffix(_INFO))
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


def _merge(video: list[LibraryEntry], audio: list[LibraryEntry]) -> list[LibraryEntry]:
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


def all_entries(video_dir: Path, audio_dir: Path) -> list[LibraryEntry]:
    """Return library entries (video and audio merged by id), newest upload first.

    Cached until a directory mtime changes or `invalidate_cache()` is called. A rebuild walks each root once and
    parses only sidecars that are new or changed since the persisted index was written.
    """
    with _lock:
        cache_key = (str(video_dir), str(audio_dir))
        v_mtime, a_mtime = _dir_mtime(video_dir), _dir_mtime(audio_dir)
        cached = _cache.get(cache_key)
        if cached is not None and cached[0] == v_mtime and cached[1] == a_mtime:
            return cached[2]
        index = _index.read(dict)
        fresh: dict = {}
        entries = _merge(_scan_root(video_dir, "video", index, fresh), _scan_root(audio_dir, "audio", index, fresh))
        if set(fresh) != set(index) or any(fresh[p] is not index.get(p) for p in fresh):
            _index.update(lambda data: _replace(data, fresh), defer=True)
        _cache[cache_key] = (v_mtime, a_mtime, entries)
        return entries


def invalidate_cache() -> None:
    """Force a rebuild on the next all_entries() call; the persisted index still saves the parsing."""
    with _lock:
        _cache.clear()


def _sidecar_for(media: Path) -> Path:
    return media.with_name(media.stem + _INFO)


def refresh(paths: Iterable[Path | str]) -> None:
    """Index the sidecars next to ``paths`` (files a download just wrote); nothing else is read."""
    records = {}
    for media in map(Path, paths):
        sidecar = _sidecar_for(media)
        try:
            st = sidecar.stat()
        except OSError:
            continue
        record = _parse(str(sidecar), st.st_mtime, st.st_size)
        if record:
            records[str(sidecar)] = record
    if records:
        _index.update(lambda data: _replace(data, records, keep=True), defer=True)
    invalidate_cache()


def normalise_thumbnail(media: Path) -> Path | None:
    """Make the thumbnail yt-dlp wrote next to ``media`` a JPEG named after it, so it survives and loads offline."""
    jpg = media.with_suffix(".jpg")
    if jpg.exists():
        return jpg
    for ext in (".webp", ".png"):
        source = media.with_suffix(ext)
        if not source.exists():
            continue
        try:
            from PIL import Image

            with Image.open(source) as img:
                img.convert("RGB").save(jpg, "JPEG", quality=90)
            source.unlink()
            return jpg
        except (OSError, ValueError):
            logger.debug("library: could not convert thumbnail %s", source)
            return source
    return None


def finish_download(paths: Iterable[Path | str]) -> LibraryEntry | None:
    """After a download: normalise its thumbnail, index it, and return its slim entry (None if it has no sidecar).

    ``paths`` are the files yt-dlp finished; the last one with a sidecar is the final media file.
    """
    files = [Path(p) for p in paths]
    for media in files:
        if _sidecar_for(media).exists():
            normalise_thumbnail(media)
    refresh(files)
    for media in reversed(files):
        sidecar = str(_sidecar_for(media))
        record = _index.read(lambda data: data.get(sidecar))
        if record:
            entry: LibraryEntry = {**record["entry"], "_local_path": str(media), "_sidecar_path": sidecar}
            jpg = media.with_suffix(".jpg")
            if jpg.exists():
                entry["_thumb_path"] = str(jpg)
            return entry
    return None


# ── deleting files ─────────────────────────────────────────────────────────────────────────────────────────────


@dataclass
class DeleteResult:
    """What `safe_delete` did: files removed, files refused or failed with a reason, bytes freed."""

    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    freed: int = 0


def forms(entry: LibraryEntry) -> dict[str, tuple[str | None, str | None]]:
    """The forms an entry has on disk, `{"video"|"audio": (media, sidecar)}`; empty when its file is missing."""
    out: dict[str, tuple[str | None, str | None]] = {}
    if entry.get("_missing_file"):
        return out
    kind = entry.get("_local_type")
    if kind in ("video", "audio"):
        out[kind] = (entry.get("_local_path"), entry.get("_sidecar_path"))
    if entry.get("_has_audio"):
        out["audio"] = (entry.get("_audio_path"), entry.get("_audio_sidecar_path"))
    return out


def form_sizes(entry: LibraryEntry) -> dict[str, int]:
    """Bytes of each form's media file."""
    sizes = {}
    if entry.get("_local_type") and not entry.get("_missing_file"):
        sizes[entry["_local_type"]] = entry.get("_size", 0)
    if entry.get("_has_audio"):
        sizes["audio"] = entry.get("_audio_size", 0)
    return sizes


def total_size(entry: LibraryEntry) -> int:
    return sum(form_sizes(entry).values())


def _refusal(path: str, roots: list[Path]) -> str | None:
    """Why ``path`` may not be deleted, or None. It must sit inside a root with no symlink on the way and no `..`."""
    candidate = Path(path)
    if ".." in candidate.parts:
        return "path contains .."
    absolute = Path(os.path.abspath(candidate))
    for root in roots:
        try:
            relative = absolute.relative_to(Path(os.path.abspath(root)))
        except ValueError:
            continue
        walk = Path(os.path.abspath(root))
        for part in relative.parts:
            walk = walk / part
            if walk.is_symlink():
                return "symlink"
        if relative.parts and absolute.resolve().is_relative_to(root.resolve()):
            return None
    return "outside the library folders"


_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$")


def _group(sidecar: str | None, media: str | None, deleting: set[str], with_media: bool) -> list[str]:
    """Files to delete for one form: the media, its sidecar, and thumbnails/subtitles that share its stem.

    The sidecar group is left alone when another media file with the same stem survives (one folder holding
    both a video and an audio file of the same name).
    """
    files = [media] if with_media and media else []
    anchor = Path(sidecar) if sidecar else (Path(media) if media else None)
    if anchor is None:
        return files
    stem = anchor.name.removesuffix(_INFO) if sidecar else anchor.stem
    try:
        names = os.listdir(anchor.parent)
    except OSError:
        return files
    aux = []
    for name in names:
        full = str(anchor.parent / name)
        base, ext = os.path.splitext(name)
        ext = ext.lower()
        if base == stem and ext in _MEDIA_EXTS and full not in deleting and with_media:
            return files
        if name == stem + _INFO or (with_media and base == stem and ext in _IMAGE_EXTS):
            aux.append(full)
        elif with_media and ext in _SUBTITLE_EXTS and base.startswith(stem + ".") and _LANG.match(base[len(stem) + 1:]):
            aux.append(full)
    return files + aux


def safe_delete(entry: LibraryEntry, roots: Iterable[Path], which: str) -> DeleteResult:
    """Delete files of ``entry``; ``which`` is video | audio | both | entry_only (sidecars only, media stays).

    Every path must lie inside one of ``roots`` without symlinks or `..`; anything else is reported in `failed`
    and left alone. Only the media, its `.info.json` and the thumbnails/subtitles sharing its stem are touched.
    A missing file is not an error. The index and the in-memory list are updated.
    """
    if which not in ("video", "audio", "both", "entry_only"):
        raise ValueError(f"unknown delete choice {which!r}")
    root_list = [Path(r) for r in roots]
    have = forms(entry)
    chosen = list(have) if which in ("both", "entry_only") else [which] if which in have else []
    if not have:  # the file is gone: removing the entry means removing its sidecar
        sidecar = entry.get("_sidecar_path")
        wanted = _group(sidecar, None, set(), with_media=True) if sidecar else []
    else:
        deleting = {m for f in chosen if (m := have[f][0])}
        wanted = [p for f in chosen for p in _group(have[f][1], have[f][0], deleting, which != "entry_only")]
    result = DeleteResult()
    for path in dict.fromkeys(wanted):
        reason = _refusal(path, root_list)
        if reason:
            result.failed.append((path, reason))
            continue
        try:
            size = os.lstat(path).st_size
            os.unlink(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            result.failed.append((path, str(exc)))
            continue
        result.removed.append(path)
        result.freed += size
    gone = [p for p in result.removed if p.endswith(_INFO)]
    if gone:
        _index.update(lambda data: bool([data.pop(p, None) for p in gone]), defer=True)
    invalidate_cache()
    return result
