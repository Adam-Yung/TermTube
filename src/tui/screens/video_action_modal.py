from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.entries import Entry
from src.tui.fmt import escape_markup

_ACTIONS = [
    ("watch",         "▶",  "Watch video  [dim](v)[/dim]"),
    ("watch_quality", "▶·", "Watch — choose quality…  [dim](V)[/dim]"),
    ("audio",         "♪",  "Play audio  [dim](a)[/dim]"),
    ("audio_quality", "♪·", "Play audio — choose quality…  [dim](A)[/dim]"),
    ("enqueue",       "♪+", "Add audio to queue  [dim](e)[/dim]"),
    ("download",      "↓",  "Download…  [dim](d)[/dim]"),
    ("channel",       "📺", "Browse channel  [dim](c)[/dim]"),
    ("copy_url",      "⎘",  "Copy video URL  [dim](y)[/dim]"),
    ("playlist",      "+",  "Add to playlist  [dim](p)[/dim]"),
    ("browser",       "🌐", "Open in browser  [dim](b)[/dim]"),
]


class _ActionItem(ListItem):
    def __init__(self, key: str, icon: str, label: str) -> None:
        super().__init__()
        self.action_key = key
        self._icon = icon
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold #888888]{self._icon:3}[/bold #888888] {self._label}",
            markup=True,
        )


class VideoActionModal(ModalScreen[str | None]):
    """Action picker for a selected video. Returns an action key string or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("j",      "cursor_down", show=False),
        Binding("k",      "cursor_up",   show=False),
    ]

    def __init__(
        self, entry: Entry, *, hide: set[str] = frozenset(), labels: dict[str, str] | None = None
    ) -> None:
        super().__init__()
        self._entry = entry
        self._hide = hide
        self._labels = labels or {}

    def compose(self) -> ComposeResult:
        title = (self._entry.get("title") or "Video")[:50]
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="vaction-dialog", classes="dialog"):
            yield Static(
                f"[bold white]{escape_markup(title)}[/bold white]",
                id="vaction-title",
                markup=True,
            )
            if channel:
                yield Static(
                    f"[dim]{escape_markup(channel)}[/dim]",
                    id="vaction-channel",
                    markup=True,
                )
            yield ListView(id="vaction-list", classes="dialog-list")
            yield Static(
                "[dim]↑↓ / jk[/dim] navigate  ·  [dim]Enter[/dim] select  ·  [dim]Esc[/dim] cancel",
                id="vaction-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        lv = self.query_one("#vaction-list", ListView)
        for key, icon, label in _ACTIONS:
            if key in self._hide:
                continue
            lv.append(_ActionItem(key, icon, self._labels.get(key, label)))
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, _ActionItem):
            self.dismiss(event.item.action_key)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one("#vaction-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#vaction-list", ListView).action_cursor_up()
