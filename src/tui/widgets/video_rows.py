"""The widgets a list mounts: entry rows, group headers and the click messages rows send the panel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.events import Click
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from src.entries import Entry
from src.tui.fmt import escape_markup
from src.tui.widgets.action_bar import THEME_COLORS
from src.tui.widgets.row_markup import row_markup


class _ItemClicked(Message):
    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry


class _ItemDoubleClicked(Message):
    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry


class HeaderListItem(ListItem):
    """A group label between rows (a day in History). Disabled, so the cursor never lands on it."""

    def __init__(self, label: str) -> None:
        super().__init__(disabled=True)
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(f"[bold #888888]{escape_markup(self._label)}[/bold #888888]", markup=True)


class VideoListItem(ListItem):
    def __init__(self, entry: Entry, *, marked: bool = False, playing: bool = False) -> None:
        super().__init__()
        self.entry = entry
        self.marked = marked
        self.playing = playing
        self._cached_markup: str = ""

    def set_marked(self, marked: bool) -> None:
        self.marked = marked
        self.refresh_markup()

    def refresh_markup(self) -> None:
        self._cached_markup = self._build_markup()
        try:
            self.query_one(Static).update(self._cached_markup)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        self._cached_markup = self._build_markup()
        yield Static(self._cached_markup, markup=True, shrink=True)

    def on_click(self, event: Click) -> None:
        event.stop()
        event.prevent_default()
        self.post_message(_ItemClicked(self.entry))

    def on_double_click(self, event: Click) -> None:
        event.stop()
        event.prevent_default()
        if isinstance(self.parent, ListView):
            self.parent.index = self.parent.children.index(self)
        self.post_message(_ItemDoubleClicked(self.entry))

    def _build_markup(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"
        color = THEME_COLORS.get(theme, "#ff6666")
        return row_markup(self.entry, color, playing=self.playing, marked=self.marked)
