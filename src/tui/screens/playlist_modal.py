"""PlaylistModal — manage playlist membership for a video."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static


class PlaylistModal(ModalScreen[None]):
    """Modal to add/remove a video from playlists, or create a new one."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=True),
        Binding("n",      "new_playlist",  "New playlist", show=True),
        Binding("j",      "cursor_down",   show=False),
        Binding("k",      "cursor_up",     show=False),
    ]

    def __init__(self, entry: dict) -> None:
        super().__init__()
        self._entry = entry
        self._video_id = entry.get("id", "")

    def compose(self) -> ComposeResult:
        title = self._entry.get("title", self._video_id)
        with Vertical(id="playlist-dialog"):
            yield Static(
                f"🎵  Playlists — [dim]{title[:50]}[/dim]",
                id="playlist-title",
                markup=True,
            )
            yield ListView(id="playlist-list")
            yield Input(
                placeholder="New playlist name… (press Enter)",
                id="playlist-new-input",
            )
            yield Static(
                "[dim]Enter[/dim] toggle  ·  [dim]n[/dim] new  ·  [dim]Esc[/dim] close",
                id="playlist-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#playlist-list", ListView).focus()

    def _refresh_list(self) -> None:
        from src import playlist
        lv = self.query_one("#playlist-list", ListView)
        lv.clear()
        names = playlist.list_names()
        if not names:
            lv.append(ListItem(Static("[dim]No playlists yet — press n to create one[/dim]", markup=True)))
            return
        for name in names:
            in_pl = playlist.is_in_playlist(name, self._video_id)
            check = "[#44ff44]✓[/] " if in_pl else "  "
            count = len(playlist.get_playlist(name))
            item = ListItem(
                Static(
                    f"{check}[bold]{name}[/bold]  [dim]{count} videos[/dim]",
                    markup=True,
                )
            )
            item._pl_name = name  # type: ignore[attr-defined]
            lv.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if not hasattr(item, "_pl_name"):
            return
        from src import playlist
        name = item._pl_name  # type: ignore[attr-defined]
        if playlist.is_in_playlist(name, self._video_id):
            playlist.remove_video(name, self._video_id)
            self.app.notify(f'Removed from "{name}"')
        else:
            playlist.add_video(name, self._video_id)
            self.app.notify(f'Added to "{name}"')
        self._refresh_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if not name:
            return
        from src import playlist
        playlist.create(name)
        playlist.add_video(name, self._video_id)
        event.input.value = ""
        self._refresh_list()
        self.app.notify(f'Created playlist "{name}" and added video')
        self.query_one("#playlist-list", ListView).focus()

    def action_new_playlist(self) -> None:
        self.query_one("#playlist-new-input", Input).focus()

    def action_cursor_down(self) -> None:
        self.query_one("#playlist-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#playlist-list", ListView).action_cursor_up()

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
