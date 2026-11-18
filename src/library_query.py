"""Library search: `key:value` tokens on top of free text. Pure; the list filter calls `rank` in Library views."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from src import fuzzy, library
from src.entries import Entry

_KEYS = ("type", "dur", "by", "year", "pl", "dl")
_DURATION = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")
_CLOCK = re.compile(r"(?:(\d+):)?(\d+):(\d{2})$")
_FIELD_WEIGHTS = {"title": 1.0, "people": 0.5, "tags": 0.3, "description": 0.25}


@dataclass
class Query:
    """A parsed query: free-text tokens plus predicates (each takes the entry and the playlist-membership lookup)."""

    free: list[str] = field(default_factory=list)
    checks: list[Callable[[Entry, Callable[[str], list[str]]], bool]] = field(default_factory=list)
    uses_playlists: bool = False


def _words(text: str) -> list[str]:
    """Split on spaces; a double-quoted run (also after `key:`) stays one word. An unclosed quote runs to the end."""
    words, current, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        elif ch.isspace() and not quoted:
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        words.append("".join(current))
    return words


def parse_duration(text: str) -> int | None:
    """Seconds for `90`, `90s`, `10m`, `1h30m` or `1:30:00` / `10:05`; None when it is not a duration."""
    text = text.strip().lower()
    clock = _CLOCK.match(text)
    if clock:
        hours, minutes, seconds = (int(g or 0) for g in clock.groups())
        return hours * 3600 + minutes * 60 + seconds
    match = _DURATION.match(text)
    if not text or not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _people(entry: Entry) -> str:
    return fuzzy.fold(f"{entry.get('uploader') or ''} {entry.get('channel') or ''}")


def _check_for(key: str, value: str):
    """The predicate for one token, or None when ``value`` is not valid for ``key``."""
    folded = fuzzy.fold(value)
    if key == "type" and folded in ("audio", "video"):
        return lambda e, _pl: folded in library.kinds(e)
    if key == "dl" and folded in ("yes", "no"):
        want = folded == "yes"
        return lambda e, _pl: bool(e.get("_local_path") and not e.get("_missing_file")) == want
    if key == "dur" and value[:1] in "<>":
        seconds = parse_duration(value[1:])
        if seconds is None:
            return None
        if value[0] == "<":
            return lambda e, _pl: e.get("duration") is not None and e["duration"] < seconds
        return lambda e, _pl: e.get("duration") is not None and e["duration"] > seconds
    if key == "year" and re.fullmatch(r"\d{4}", value):
        return lambda e, _pl: (e.get("upload_date") or "").startswith(value)
    if key == "by" and folded:
        return lambda e, _pl: folded in _people(e)
    if key == "pl" and folded:
        return lambda e, pl: any(folded in fuzzy.fold(name) for name in pl(e.get("id", "")))
    return None


def parse(text: str) -> Query:
    """Split ``text`` into tokens and free text. A token that is not valid (`type:foo`, `dur:soon`) stays free text."""
    query = Query()
    for word in _words(text):
        key, sep, value = word.partition(":")
        check = _check_for(key.lower(), value) if sep and key.lower() in _KEYS else None
        if check is None:
            query.free.append(fuzzy.fold(word))
        else:
            query.checks.append(check)
            query.uses_playlists = query.uses_playlists or key.lower() == "pl"
    return query


def _fields(entry: Entry) -> list[tuple[str, float]]:
    tags = " ".join(entry.get("tags") or entry.get("keywords") or [])
    texts = {
        "title": entry.get("title") or "",
        "people": _people(entry),
        "tags": tags,
        "description": entry.get("description") or "",
    }
    return [(fuzzy.fold(text), _FIELD_WEIGHTS[name]) for name, text in texts.items()]


def rank(entries: list[Entry], text: str, membership: Callable[[], dict[str, list[str]]] | None = None) -> list[Entry]:
    """Entries passing every token and matching all free words, best first. Empty ``text`` returns all of them.

    ``membership`` returns {video id: playlist names}; it is called once, and only when a `pl:` token is used.
    """
    query = parse(text)
    if not query.free and not query.checks:
        return list(entries)
    names = membership() if query.uses_playlists and membership else {}

    def playlists(video_id: str) -> list[str]:
        return names.get(video_id, [])

    scored: list[tuple[float, int, Entry]] = []
    for index, entry in enumerate(entries):
        if not all(check(entry, playlists) for check in query.checks):
            continue
        score = fuzzy.score_tokens(query.free, _fields(entry)) if query.free else 1.0
        if score:
            scored.append((-score, index, entry))
    scored.sort(key=lambda item: item[:2])
    return [entry for _, _, entry in scored]
