"""Footer of the paged list: ◀  Page N / M  ▶, clickable."""

from __future__ import annotations

from rich.text import Text
from textual.events import Click
from textual.message import Message
from textual.widget import Widget

from src.strings import text
from src.tui.fmt import escape_markup


class PageIndicator(Widget):
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
        self._note: str = ""

    def update_state(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        next_ready: bool | None = None,
        note: str | None = None,
    ) -> None:
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total
        if next_ready is not None:
            self._next_ready = next_ready
        if note is not None:
            self._note = note
        self.refresh()

    def render(self) -> Text:
        prev_arrow = "◀" if self._current > 1 else "·"
        next_arrow = "▶" if self._next_ready else "·"
        note = f"  ·  {escape_markup(self._note)}" if self._note else ""
        page = text("page_indicator.page", current=self._current, total=self._total)
        return Text.from_markup(
            f"[dim]{prev_arrow}  {page}  {next_arrow}{note}[/dim]"
        )

    def on_click(self, event: Click) -> None:
        width = self.size.width
        if width <= 0:
            return
        mid = width // 2
        if event.x < mid:
            if self._current > 1:
                self.post_message(self.PrevPage())
        else:
            if self._next_ready:
                self.post_message(self.NextPage())
