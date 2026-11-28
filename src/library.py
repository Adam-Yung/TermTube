"""Library page data: a slim, persisted index of the download dirs' yt-dlp `.info.json` sidecars, and file deletion."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from src import library_scan, logger
from src.entries import Entry, LibraryEntry
from src.library_scan import IMAGE_EXTS, INFO, MEDIA_EXTS
from src.plat import get_cache_dir
from src.store import JsonStore
from src.strings import text

INDEX_PATH = get_cache_dir() / "library.json"

_SUBTITLE_EXTS = (".vtt", ".srt", ".ass", ".lrc")

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


def all_entries(video_dir: Path, audio_dir: Path) -> list[LibraryEntry]:
    """Return library entries (video and audio merged by id), newest upload first.

    Cached until a directory mtime changes or `invalidate_cache()` is called. A rebuild walks each root once and
    parses only sidecars that are new or changed since the persisted index was written.
    """
    with _lock:
        cache_key = (str(video_dir), str(audio_dir))
        v_mtime, a_mtime = library_scan.dir_mtime(video_dir), library_scan.dir_mtime(audio_dir)
        cached = _cache.get(cache_key)
        if cached is not None and cached[0] == v_mtime and cached[1] == a_mtime:
            return cached[2]
        index = _index.read(dict)
        fresh: dict = {}
        video = library_scan.scan_root(video_dir, "video", index, fresh)
        audio = library_scan.scan_root(audio_dir, "audio", index, fresh)
        entries = library_scan.merge(video, audio)
        if set(fresh) != set(index) or any(fresh[p] is not index.get(p) for p in fresh):
            _index.update(lambda data: _replace(data, fresh), defer=True)
        _cache[cache_key] = (v_mtime, a_mtime, entries)
        return entries


def invalidate_cache() -> None:
    """Force a rebuild on the next all_entries() call; the persisted index still saves the parsing."""
    with _lock:
        _cache.clear()


_LOCAL_KEYS = ("_local_path", "_local_type", "_size", "_sidecar_path", "_has_audio", "_audio_path", "_audio_size",
               "_audio_sidecar_path", "_thumb_path")


def kinds(entry: Entry) -> set[str]:
    """The forms a downloaded row exists in: ``{"video"}``, ``{"audio"}`` or both. Empty when it is not downloaded."""
    if not entry.get("_local_type"):
        return set()
    return {entry["_local_type"]} | ({"audio"} if entry.get("_has_audio") else set())


def of_kind(entries: list[LibraryEntry], kind: str) -> list[LibraryEntry]:
    """The entries that exist as ``kind`` (`video` or `audio`); every entry for an empty ``kind``."""
    return [e for e in entries if not kind or kind in kinds(e)]


def counts(entries: list[LibraryEntry]) -> dict[str, int]:
    """Entries per rail collection: all (key ``""``), video and audio."""
    return {"": len(entries), "video": len(of_kind(entries, "video")), "audio": len(of_kind(entries, "audio"))}


def attach_local(rows: list[Entry], library_entries: Iterable[LibraryEntry]) -> list[Entry]:
    """Copies of ``rows`` marked with their download state: `_dl` is `video`, `audio`, `both` or `""` (stream only).

    A downloaded row also gets the `_local_*` fields, so playing it and the detail panel use the file on disk.
    """
    by_id = {e["id"]: e for e in library_entries if not e.get("_missing_file")}
    out = []
    for row in rows:
        found = by_id.get(row.get("id", ""))
        have = kinds(found) if found else set()
        dl = "both" if len(have) == 2 else next(iter(have), "")
        extra = {k: found[k] for k in _LOCAL_KEYS if found and k in found} if have else {}
        out.append({**row, **extra, "_dl": dl})
    return out


def _sidecar_for(media: Path) -> Path:
    return media.with_name(media.stem + INFO)


def refresh(paths: Iterable[Path | str]) -> None:
    """Index the sidecars next to ``paths`` (files a download just wrote); nothing else is read."""
    records = {}
    for media in map(Path, paths):
        sidecar = _sidecar_for(media)
        try:
            st = sidecar.stat()
        except OSError:
            continue
        record = library_scan.parse_sidecar(str(sidecar), st.st_mtime, st.st_size)
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
        return text("library.refuse_dotdot")
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
                return text("library.refuse_symlink")
        if relative.parts and absolute.resolve().is_relative_to(root.resolve()):
            return None
    return text("library.refuse_outside")


_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$")


def _group(sidecar: str | None, media: str | None, deleting: set[str]) -> list[str]:
    """Files to delete for one form: the media, its sidecar, and thumbnails/subtitles that share its stem.

    The sidecar group is left alone when another media file with the same stem survives (one folder holding
    both a video and an audio file of the same name).
    """
    files = [media] if media else []
    anchor = Path(sidecar) if sidecar else (Path(media) if media else None)
    if anchor is None:
        return files
    stem = anchor.name.removesuffix(INFO) if sidecar else anchor.stem
    try:
        names = os.listdir(anchor.parent)
    except OSError:
        return files
    aux = []
    for name in names:
        full = str(anchor.parent / name)
        base, ext = os.path.splitext(name)
        ext = ext.lower()
        if base == stem and ext in MEDIA_EXTS and full not in deleting:
            return files
        if name == stem + INFO or (base == stem and ext in IMAGE_EXTS):
            aux.append(full)
        elif ext in _SUBTITLE_EXTS and base.startswith(stem + ".") and _LANG.match(base[len(stem) + 1:]):
            aux.append(full)
    return files + aux


def _files_to_delete(entry: LibraryEntry, which: str) -> list[str]:
    have = forms(entry)
    if not have:  # the file is gone: removing the entry means removing its sidecar
        sidecar = entry.get("_sidecar_path")
        return _group(sidecar, None, set()) if sidecar else []
    chosen = list(have) if which == "both" else [which] if which in have else []
    deleting = {m for f in chosen if (m := have[f][0])}
    return [p for f in chosen for p in _group(have[f][1], have[f][0], deleting)]


def _delete_one(path: str, roots: list[Path], result: DeleteResult) -> None:
    reason = _refusal(path, roots)
    if reason:
        result.failed.append((path, reason))
        return
    try:
        size = os.lstat(path).st_size
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        result.failed.append((path, str(exc)))
        return
    result.removed.append(path)
    result.freed += size


def safe_delete(entry: LibraryEntry, roots: Iterable[Path], which: str) -> DeleteResult:
    """Delete files of ``entry``; ``which`` is video | audio | both.

    Every path must lie inside one of ``roots`` without symlinks or `..`; anything else is reported in `failed`
    and left alone. Only the media, its `.info.json` and the thumbnails/subtitles sharing its stem are touched.
    A missing file is not an error. The index and the in-memory list are updated.
    """
    if which not in ("video", "audio", "both"):
        raise ValueError(f"unknown delete choice {which!r}")
    root_list = [Path(r) for r in roots]
    result = DeleteResult()
    for path in dict.fromkeys(_files_to_delete(entry, which)):
        _delete_one(path, root_list, result)
    gone = [p for p in result.removed if p.endswith(INFO)]
    if gone:
        _index.update(lambda data: bool([data.pop(p, None) for p in gone]), defer=True)
    invalidate_cache()
    return result
