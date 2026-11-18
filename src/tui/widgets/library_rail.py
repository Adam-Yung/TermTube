from __future__ import annotations

from typing import NamedTuple

from rich.text import Text
from textual.binding import Binding
from textual.events import Click
from textual.message import Message
from textual.widget import Widget

from src.tui.widgets.action_bar import THEME_COLORS

NEW_PLAYLIST = "__new__"


class RailItem(NamedTuple):
    view: str
    label: str
    count: int | None = None


class LibraryRail(Widget, can_focus=True):
    """The Library tab's collection list: one row per entry, or a one-line selector when ``narrow``.

    Moving the cursor only highlights; Enter (or a click) posts ``Chosen``. ``current`` is the entry the list shows.
    """

    OWNS_NAV_KEYS = True

    BINDINGS = [
        Binding("j,down", "cursor_down", show=False),
        Binding("k,up", "cursor_up", show=False),
        Binding("g", "cursor_first", show=False),
        Binding("G", "cursor_last", show=False),
        Binding("enter", "choose", show=False),
        Binding("l,right", "to_list", show=False),
        Binding("tab", "screen.rail_toggle", show=False),
    ]

    class Chosen(Message):
        def __init__(self, view: str) -> None:
            super().__init__()
            self.view = view

    class Moved(Message):
        """The cursor is on another entry."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[RailItem] = []
        self._cursor = 0
        self._current = ""
        self.narrow = False

    @property
    def highlighted(self) -> RailItem | None:
        return self._items[self._cursor] if self._items else None

    @property
    def current(self) -> str:
        return self._current

    def set_items(self, items: list[RailItem], current: str) -> None:
        """Replace the entries, keeping the cursor on the same view when it still exists."""
        kept = self.highlighted.view if self.highlighted else current
        self._items = items
        self._current = current
        views = [i.view for i in items]
        self._cursor = views.index(kept) if kept in views else (views.index(current) if current in views else 0)
        self.refresh(layout=True)

    def set_current(self, view: str) -> None:
        self._current = view
        views = [i.view for i in self._items]
        if view in views:
            self._cursor = views.index(view)
        self.refresh()

    def set_narrow(self, narrow: bool) -> None:
        self.narrow = narrow
        self.set_class(narrow, "-narrow")
        self.refresh(layout=True)

    def _move(self, to: int) -> None:
        if self._items:
            self._cursor = max(0, min(to, len(self._items) - 1))
            self.refresh()
            self.post_message(self.Moved())

    def action_cursor_down(self) -> None:
        self._move(self._cursor + 1)

    def action_cursor_up(self) -> None:
        self._move(self._cursor - 1)

    def action_cursor_first(self) -> None:
        self._move(0)

    def action_cursor_last(self) -> None:
        self._move(len(self._items) - 1)

    def action_choose(self) -> None:
        if self.highlighted:
            self.post_message(self.Chosen(self.highlighted.view))

    def action_to_list(self) -> None:
        self.screen.action_rail_toggle()

    def _window_start(self) -> int:
        height = max(self.size.height, 1)
        return max(0, min(self._cursor - height + 1, len(self._items) - height)) if self._cursor >= height else 0

    def on_click(self, event: Click) -> None:
        event.stop()
        index = self._cursor if self.narrow else self._window_start() + event.y
        if 0 <= index < len(self._items):
            self._cursor = index
            self.refresh()
            self.action_choose()

    def _line(self, item: RailItem, width: int, *, cursor: bool, accent: str) -> Text:
        count = "" if item.count is None else str(item.count)
        label = item.label[: max(width - len(count) - 3, 1)]
        pad = " " * max(width - len(label) - len(count) - 3, 1)
        line = Text(f" {label}{pad}{count} ")
        if item.view == self._current:
            line.stylize(f"bold {accent}")
        if cursor:
            line.stylize("bold white on #16162a" if self.has_focus else "underline")
        return line

    def render(self) -> Text:
        try:
            accent = THEME_COLORS.get(self.app.config.theme, "#ff6666")
        except Exception:
            accent = "#ff6666"
        width = max(self.size.width, 8)
        if self.narrow:
            item = self.highlighted
            if item is None:
                return Text("")
            position = f"▸ {self._cursor + 1}/{len(self._items)}"
            line = self._line(item, width - 2 - len(position), cursor=False, accent=accent)
            return Text("◂ ") + line + Text(position, style="dim")
        start = self._window_start()
        rows = self._items[start : start + max(self.size.height, 1)]
        out = Text()
        for offset, item in enumerate(rows):
            if offset:
                out.append("\n")
            out.append_text(self._line(item, width - 1, cursor=start + offset == self._cursor, accent=accent))
        return out
