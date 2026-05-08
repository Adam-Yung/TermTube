"""TermTube v2 — BookmarkModal.

Lists all bookmarks for the currently-playing video.
Selecting one returns the bookmark's position (float seconds) to the caller,
which then calls PlayerSession.seek() to jump there.
Deleting one calls history.remove_bookmark() and refreshes the list.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

import history as _history
from tui.components.progress_bar import _fmt_time


class BookmarkModal(ModalScreen[float | None]):
    """Jump-to-bookmark dialog for the currently playing video."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
        Binding("d", "delete_selected", "Delete", show=True),
    ]

    DEFAULT_CSS = """
    BookmarkModal {
        align: center middle;
    }
    #bm-box {
        width: 56;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #bm-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #bm-list {
        height: 10;
        border: solid $surface-lighten-1;
        margin-bottom: 1;
    }
    #bm-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #bm-close {
        width: 100%;
    }
    """

    def __init__(self, video_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._video_id = video_id
        self._bookmarks: list[dict] = []

    def compose(self) -> ComposeResult:
        with Static(id="bm-box"):
            yield Static("◆  Bookmarks", id="bm-title")
            yield ListView(id="bm-list")
            yield Static("Enter: jump  ·  d: delete", id="bm-hint")
            yield Button("Close", variant="default", id="bm-close")

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._bookmarks = _history.get_bookmarks(self._video_id)
        lv = self.query_one("#bm-list", ListView)
        lv.clear()
        if not self._bookmarks:
            lv.append(ListItem(Label("[dim]No bookmarks yet[/dim]")))
            return
        for bm in self._bookmarks:
            pos = bm.get("position", 0.0)
            label_text = bm.get("label") or _fmt_time(pos)
            item = ListItem(Label(f"◆  {_fmt_time(pos)}  —  {label_text}"))
            item.data = pos  # type: ignore[attr-defined]
            lv.append(item)
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        pos = getattr(event.item, "data", None)
        if isinstance(pos, (int, float)):
            self.dismiss(float(pos))

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_delete_selected(self) -> None:
        lv = self.query_one("#bm-list", ListView)
        item = lv.highlighted_child
        if item is None:
            return
        pos = getattr(item, "data", None)
        if isinstance(pos, (int, float)):
            _history.remove_bookmark(self._video_id, float(pos))
            self._reload()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
