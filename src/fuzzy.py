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


def score_tokens(tokens: list[str], fields: list[tuple[str, float]]) -> float:
    """Sum over ``tokens`` of the best score in the folded ``fields`` (text, weight). 0 if a token is absent."""
    total = 0.0
    for token in tokens:
        score = max(_token_score(token, text) * weight for text, weight in fields)
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
        score = score_tokens(tokens, [(title, 1.0), (other, _SECONDARY_WEIGHT)])
        if score:
            scored.append((-score, index, entry))
    scored.sort(key=lambda item: item[:2])
    return [entry for _, _, entry in scored]


def rank_strings(texts: list[str], query: str) -> list[str]:
    """`rank` for plain strings: those matching every token of `query`, best first."""
    return [e["title"] for e in rank([{"title": t} for t in texts], query)]
