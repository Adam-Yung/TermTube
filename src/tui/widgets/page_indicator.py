"""PageIndicator — compact page navigation footer for the paged video list."""

from __future__ import annotations

from rich.text import Text

from textual.message import Message
from textual.events import Click
from textual.widget import Widget


class PageIndicator(Widget):
    """Footer bar rendering: ◀  Page N / M  [status]  ▶"""

    DEFAULT_CSS = """
    PageIndicator {
        height: 1;
        dock: bottom;
        text-align: center;
        color: $text-muted;
    }
    """

    class PrevPage(Message):
        pass

    class NextPage(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current: int = 1
        self._total: int = 1
        self._next_ready: bool = False
        self._prefetching: bool = False

    def update_state(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        next_ready: bool | None = None,
        prefetching: bool | None = None,
    ) -> None:
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total
        if next_ready is not None:
            self._next_ready = next_ready
        if prefetching is not None:
            self._prefetching = prefetching
        self.refresh()

    def render(self) -> Text:
        prev_arrow = "◀" if self._current > 1 else "·"
        next_arrow = "▶" if self._next_ready else "·"
        status = "  loading next…" if (self._prefetching and not self._next_ready) else ""

        return Text.from_markup(
            f"[dim]{prev_arrow}  Page {self._current} / {self._total}{status}  {next_arrow}[/dim]"
        )

    def on_click(self, event: Click) -> None:
        width = self.size.width
        if width <= 0:
            return
        x = event.x
        if x < width // 3:
            if self._current > 1:
                self.post_message(self.PrevPage())
        elif x > (width * 2) // 3:
            if self._next_ready:
                self.post_message(self.NextPage())
