"""Query matching for the list filter: case- and accent-insensitive tokens, every token must match."""

from __future__ import annotations

import unicodedata

from src.entries import Entry

_PREFIX = 100.0
_WORD_START = 60.0
_INSIDE = 20.0
_SECONDARY_WEIGHT = 0.5


def fold(text: str) -> str:
    """Casefold, and strip accents from non-ASCII text so `cafe` finds `Café`."""
    text = text.casefold()
    if text.isascii():
        return text
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _token_score(token: str, text: str) -> float:
    """Best score of `token` inside folded `text`: prefix of the field, start of a word, or anywhere. 0 if absent."""
    pos = text.find(token)
    if pos < 0:
        return 0.0
    best = _INSIDE
    while pos >= 0:
        if pos == 0:
            return _PREFIX
        if not text[pos - 1].isalnum():
            best = _WORD_START
        pos = text.find(token, pos + 1)
    return best


def _entry_score(tokens: list[str], title: str, other: str) -> float:
    total = 0.0
    for token in tokens:
        score = max(_token_score(token, title), _token_score(token, other) * _SECONDARY_WEIGHT)
        if score == 0.0:
            return 0.0
        total += score
    return total


def rank(entries: list[Entry], query: str) -> list[Entry]:
    """Entries matching every token of `query` in title or uploader/channel, best first (ties keep their order).

    An empty query returns all entries unchanged.
    """
    tokens = [fold(t) for t in query.split()]
    if not tokens:
        return list(entries)
    scored: list[tuple[float, int, Entry]] = []
    for index, entry in enumerate(entries):
        title = fold(entry.get("title") or "")
        other = fold(f"{entry.get('uploader') or ''} {entry.get('channel') or ''}")
        score = _entry_score(tokens, title, other)
        if score:
            scored.append((-score, index, entry))
    scored.sort(key=lambda item: item[:2])
    return [entry for _, _, entry in scored]
