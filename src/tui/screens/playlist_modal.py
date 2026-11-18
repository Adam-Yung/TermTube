from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from src import playlist
from src.entries import Entry
from src.strings import text
from src.tui.fmt import escape_markup


class PlaylistModal(ModalScreen[None]):
    """Modal to add/remove a video from playlists, or create a new one."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=True),
        Binding("n",      "new_playlist",  "New playlist", show=True),
        Binding("space",  "select_row",    show=False),
        Binding("j",      "cursor_down",   show=False),
        Binding("k",      "cursor_up",     show=False),
    ]

    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self._entry = entry
        self._video_id = entry.get("id", "")
        self._pending: set[str] = set()  # ids of playlists whose membership Enter will flip

    def compose(self) -> ComposeResult:
        title = self._entry.get("title", self._video_id)
        with Vertical(id="playlist-dialog", classes="dialog"):
            yield Static(
                text("playlist_modal.title", title=escape_markup(title[:50])),
                id="playlist-title",
                markup=True,
            )
            yield ListView(id="playlist-list", classes="dialog-list")
            yield Input(
                placeholder=text("playlist_modal.placeholder"),
                id="playlist-new-input",
            )
            yield Static(
                text("playlist_modal.hint"),
                id="playlist-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#playlist-list", ListView).focus()

    def _refresh_list(self) -> None:
        lv = self.query_one("#playlist-list", ListView)
        index = lv.index or 0
        lv.clear()
        playlists = playlist.list_playlists()
        if not playlists:
            lv.append(ListItem(Static(text("playlist_modal.empty"), markup=True)))
            return
        for pl in playlists:
            member = any(i["id"] == self._video_id for i in pl["items"])
            check = "[#44ff44]✓[/] " if member else "  "
            mark = "[#ffcc00]●[/] " if pl["id"] in self._pending else "  "
            count = len(pl["items"])
            item = ListItem(
                Static(
                    f"{mark}{check}[bold]{escape_markup(pl['name'])}[/bold]  "
                    + text("playlist_modal.row_count", count=count),
                    markup=True,
                )
            )
            item._pl_id = pl["id"]  # type: ignore[attr-defined]
            item._pl_name = pl["name"]  # type: ignore[attr-defined]
            item._pl_member = member  # type: ignore[attr-defined]
            lv.append(item)
        lv.index = min(index, len(playlists) - 1)

    def action_select_row(self) -> None:
        """Space: select or unselect the highlighted playlist for the next Enter."""
        item = self.query_one("#playlist-list", ListView).highlighted_child
        pid = getattr(item, "_pl_id", None)
        if pid is not None:
            self._pending ^= {pid}
            self._refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter: flip membership for every selected playlist, or for the highlighted one when none is selected."""
        rows = [i for i in self.query_one("#playlist-list", ListView).children if hasattr(i, "_pl_id")]
        chosen = [i for i in rows if i._pl_id in self._pending] or [event.item]  # type: ignore[attr-defined]
        if not hasattr(event.item, "_pl_id"):
            return
        for item in chosen:
            self._toggle(item._pl_id, item._pl_name, item._pl_member)  # type: ignore[attr-defined]
        self._pending.clear()
        self._sync_pins()
        self._refresh_list()

    def _toggle(self, pid: str, name: str, member: bool) -> None:
        if member:
            playlist.remove_items(pid, [self._video_id])
            self.app.notify(text("playlist_modal.removed", name=escape_markup(name)))
        else:
            playlist.add_items(pid, [self._entry])
            self.app.notify(text("playlist_modal.added", name=escape_markup(name)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if not name:
            return
        created = playlist.create(name, [self._entry])
        if created is None:
            self.app.notify(text("playlist_modal.exists", name=escape_markup(name)), severity="warning")
            return
        self._sync_pins()
        event.input.value = ""
        self._refresh_list()
        self.app.notify(text("playlist_modal.created", name=escape_markup(name)))
        self.query_one("#playlist-list", ListView).focus()

    def _sync_pins(self) -> None:
        """Protect the video's cached data from eviction while it is in a playlist; release it when it is in none."""
        if hasattr(self.app, "cache"):
            playlist.sync_pins(self.app.cache, [self._video_id], [self._entry])

    def action_new_playlist(self) -> None:
        self.query_one("#playlist-new-input", Input).focus()

    def action_cursor_down(self) -> None:
        self.query_one("#playlist-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#playlist-list", ListView).action_cursor_up()

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
