"""The Local tab's files: the launch folder, one folder's listing as rows, and deleting one file."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.entries import Entry
from src.plat import IS_WINDOWS
from src.strings import text

LOCAL_PREFIX = "local-"
FOLDER_PREFIX = "__dir__"
VIDEO_EXTS = frozenset({".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".mpg", ".mpeg", ".ts", ".m2ts", ".wmv",
                        ".flv", ".3gp", ".ogv"})
AUDIO_EXTS = frozenset({".mp3", ".m4a", ".opus", ".ogg", ".oga", ".flac", ".wav", ".aac", ".wma", ".aiff", ".aif",
                        ".ape", ".mka", ".alac"})
_WINDOWS_HIDDEN = 0x2
_TS_PACKET = 188
_TS_SYNC = 0x47

_launch_dir: Path | None = None


def capture_launch_dir() -> None:
    """Remember the folder TermTube was started in; the home folder when that folder is gone."""
    global _launch_dir
    try:
        _launch_dir = Path(os.getcwd())
    except OSError:
        _launch_dir = Path.home()


def launch_dir() -> Path:
    if _launch_dir is None:
        capture_launch_dir()
    return _launch_dir


def is_local_id(vid: str | None) -> bool:
    """True for the id of a file row: such an id must never reach YouTube, SponsorBlock or a thumbnail host."""
    return bool(vid) and vid.startswith(LOCAL_PREFIX)


def encodable(path: str) -> bool:
    """False for a name with undecodable bytes (Linux surrogates): it cannot be stored as JSON or passed on safely."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _digest(*parts: object) -> str:
    raw = "\0".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:20]


def clean(name: str) -> str:
    """Text as one terminal-safe line: control characters (newlines, escapes) become spaces."""
    return "".join(c if c.isprintable() else " " for c in name)


def folder_row(path: str, title: str) -> Entry:
    return {"id": FOLDER_PREFIX + _digest(path), "title": clean(title), "_is_folder": True, "_local_path": path}


def _is_mpeg_ts(path: str) -> bool:
    """`.ts` is also TypeScript: MPEG-TS has the sync byte 0x47 at the start of its first two 188-byte packets."""
    try:
        with open(path, "rb") as f:
            head = f.read(_TS_PACKET + 1)
    except OSError:
        return False
    return len(head) > _TS_PACKET and head[0] == head[_TS_PACKET] == _TS_SYNC


def _kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ts":
        return "video" if _is_mpeg_ts(path) else ""
    return "video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else ""


def _hidden(child: os.DirEntry) -> bool:
    if child.name.startswith("."):
        return True
    return IS_WINDOWS and bool(child.stat(follow_symlinks=False).st_file_attributes & _WINDOWS_HIDDEN)


def _file_row(child: os.DirEntry, kind: str) -> Entry:
    st = child.stat()
    return {"id": LOCAL_PREFIX + _digest(child.path, st.st_size, st.st_mtime_ns), "title": clean(child.name),
            "_local_path": child.path, "_local_type": kind, "_size": st.st_size, "_mtime_ns": st.st_mtime_ns}


@dataclass
class Listing:
    """One folder: rows to show (the parent first), and why the folder could not be read, if it could not."""

    entries: list[Entry] = field(default_factory=list)
    error: str = ""


def _sort_child(child: os.DirEntry, folders: list[Entry], files: list[Entry]) -> None:
    """File the child under folders or media; anything unreadable, hidden or not media is skipped."""
    try:
        if _hidden(child) or not encodable(child.path):
            return
        if child.is_dir():
            folders.append(folder_row(child.path, child.name))
        elif child.is_file() and (kind := _kind(child.path)):
            files.append(_file_row(child, kind))
    except OSError:
        pass


def _read(folder: str, cancelled: Callable[[], bool]) -> tuple[list[Entry], list[Entry]]:
    folders: list[Entry] = []
    files: list[Entry] = []
    with os.scandir(folder) as children:
        for child in children:
            if cancelled():
                break
            _sort_child(child, folders, files)
    return folders, files


def _title_key(entry: Entry) -> str:
    return entry["title"].casefold()


def list_folder(folder: str | Path, cancelled: Callable[[], bool] = lambda: False) -> Listing:
    """Rows for ``folder``: `..` (unless it is a root), its folders, then its media files, each sorted by name.

    One level only; symlinks are followed for reading, so a link loop is just another folder row.
    """
    path = os.path.abspath(folder)
    listing = Listing()
    parent = os.path.dirname(path)
    if parent != path:
        listing.entries.append({**folder_row(parent, ".."), "_is_parent": True})
    try:
        folders, files = _read(path, cancelled)
    except OSError as exc:
        listing.error = text("local_files.unreadable", reason=exc.strerror or str(exc))
        return listing
    listing.entries += sorted(folders, key=_title_key) + sorted(files, key=_title_key)
    return listing


def folder_tracks(folder: str) -> tuple[list[Entry], str]:
    """The media files directly inside ``folder``, for playing a folder row; the reason when there are none."""
    listing = list_folder(folder)
    tracks = [e for e in listing.entries if not e.get("_is_folder")]
    return tracks, listing.error or ("" if tracks else text("local_files.no_media"))


def delete_file(entry: Entry) -> str | None:
    """Delete the file of a file row; the reason it was left alone, or None when it is gone.

    Only a regular file whose size and mtime still match the listing, or a symlink (the link, never its target).
    """
    path = entry.get("_local_path")
    if not path or entry.get("_is_folder") or not is_local_id(entry.get("id")):
        return text("local_files.refuse_not_file")
    try:
        link = os.lstat(path)
        if not (stat.S_ISREG(link.st_mode) or stat.S_ISLNK(link.st_mode)):
            return text("local_files.refuse_not_file")
        target = os.stat(path) if stat.S_ISLNK(link.st_mode) else link
        if (target.st_size, target.st_mtime_ns) != (entry.get("_size"), entry.get("_mtime_ns")):
            return text("local_files.refuse_changed")
        os.unlink(path)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None
