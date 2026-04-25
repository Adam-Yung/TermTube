"""VideoActionModal — shown when user presses Enter on a video."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


# (action_key, icon, label)
_ACTIONS = [
    ("watch",         "▶",  "Watch video"),
    ("watch_quality", "▶·", "Watch — choose quality…"),
    ("listen",        "♪",  "Listen (audio only)"),
    ("listen_quality","♪·", "Listen — choose quality…"),
    ("queue",         "♪+", "Add to queue  [dim](e)[/dim]"),
    ("dl_video",      "↓",  "Download video"),
    ("dl_audio",      "↓♪", "Download audio (MP3)"),
    ("copy_url",      "⎘",  "Copy video URL  [dim](y)[/dim]"),
    ("subscribe",     "@",  "Open channel in browser"),
    ("playlist",      "+",  "Add to playlist"),
    ("browser",       "🌐", "Open in browser"),
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

    def __init__(self, entry: dict, *, hide_queue: bool = False) -> None:
        super().__init__()
        self._entry = entry
        self._hide_queue = hide_queue

    def compose(self) -> ComposeResult:
        title = (self._entry.get("title") or "Video")[:50]
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="vaction-dialog"):
            yield Static(
                f"[bold white]{title}[/bold white]",
                id="vaction-title",
                markup=True,
            )
            if channel:
                yield Static(
                    f"[dim]{channel}[/dim]",
                    id="vaction-channel",
                    markup=True,
                )
            yield ListView(id="vaction-list")
            yield Static(
                "[dim]↑↓ / jk[/dim] navigate  ·  [dim]Enter[/dim] select  ·  [dim]Esc[/dim] cancel",
                id="vaction-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        lv = self.query_one("#vaction-list", ListView)
        for key, icon, label in _ACTIONS:
            if key == "queue" and self._hide_queue:
                continue
            lv.append(_ActionItem(key, icon, label))
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
