"""The stack of searches behind the Search tab: Backspace pops to the previous results at their page and row."""

from __future__ import annotations

from dataclasses import dataclass

MAX_DEPTH = 20

SORTS = ("relevance", "date", "views")
KINDS = ("all", "video", "channel", "playlist")


@dataclass
class SearchFrame:
    query: str
    page: int = 1
    focus_id: str | None = None
    sort: str = SORTS[0]
    kind: str = KINDS[0]


class SearchStack:
    """Frames, newest last. A frame remembers where the user was when they left it."""

    def __init__(self) -> None:
        self._frames: list[SearchFrame] = []

    @property
    def query(self) -> str:
        return self._frames[-1].query if self._frames else ""

    @property
    def sort(self) -> str:
        return self._frames[-1].sort if self._frames else SORTS[0]

    @property
    def kind(self) -> str:
        return self._frames[-1].kind if self._frames else KINDS[0]

    def push(self, query: str) -> SearchFrame:
        """Make ``query`` the current search. The same query as the current one pushes nothing."""
        if self._frames and self._frames[-1].query == query:
            return self._frames[-1]
        self._frames.append(SearchFrame(query))
        del self._frames[:-MAX_DEPTH]
        return self._frames[-1]

    def pop(self) -> bool:
        """Drop the current search and go back to the one before. False when there is none."""
        if len(self._frames) < 2:
            return False
        self._frames.pop()
        return True

    def set_filter(self, field: str, value: str) -> None:
        """Change ``sort`` or ``kind`` of the current search; its results start again, so the saved position goes."""
        if self._frames:
            frame = self._frames[-1]
            setattr(frame, field, value)
            frame.page, frame.focus_id = 1, None

    def save_position(self, page: int, focus_id: str | None) -> None:
        if self._frames:
            self._frames[-1].page = page
            self._frames[-1].focus_id = focus_id

    def take_position(self) -> tuple[int, str | None]:
        """The saved page and row of the current search, once: later calls start from page 1 again."""
        if not self._frames:
            return 1, None
        frame = self._frames[-1]
        page, focus_id = frame.page, frame.focus_id
        frame.page, frame.focus_id = 1, None
        return page, focus_id

    def breadcrumb(self) -> str:
        """Hint shown above the results: the active sort and type, and the way back; empty when there is neither."""
        parts = []
        if self.sort != SORTS[0]:
            parts.append(f"sorted by {self.sort}")
        if self.kind != KINDS[0]:
            parts.append(f"{self.kind}s only")
        if len(self._frames) >= 2:
            parts.append(f"‹ {len(self._frames)} searches  ·  Backspace: back to “{self._frames[-2].query}”")
        return "  ·  ".join(parts)
