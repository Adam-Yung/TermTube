from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from src.entries import Entry
from src.strings import text
from src.tui import keymap
from src.tui.messages import AudioQueueChanged, AudioTrackChanged, PlayerStateUpdated
from src.tui.screens.mixins.app_pages import AppPagesMixin
from src.tui.screens.mixins.audio_bar import AudioBarMixin
from src.tui.screens.mixins.detail_focus import DetailFocusMixin
from src.tui.screens.mixins.item_actions import ItemActionsMixin
from src.tui.screens.mixins.list_nav import ListNavMixin
from src.tui.widgets.detail_panel import DetailPanel
from src.tui.widgets.video_list import VideoListPanel

_TRANSPORT = [
    b for b in keymap.PLAYBACK
    if b.action.startswith("audio_") and b.action not in {"audio_quality", "audio_enqueue"}
]


_LIST_NAV = [b for b in keymap.LIST_NAV if not b.action.startswith("tab_")]  # the page has no tabs


class QueueScreen(ListNavMixin, DetailFocusMixin, ItemActionsMixin, AudioBarMixin, AppPagesMixin, Screen):
    """The audio queue as a page: the playing track on top, then the upcoming ones. Edits go through ``app.audio``.

    The playing track is shown but cannot be moved or removed (``>`` skips it, ``x`` stops audio).
    The list follows the controller's broadcasts, so it stays right while tracks advance behind it.
    """

    _LIST_ID = "#queue-video-list"
    _DETAIL_ID = "#queue-detail-panel"

    BINDINGS = [
        *_LIST_NAV,
        *_TRANSPORT,
        *[b for b in keymap.ITEM_ACTIONS if b.action != "channel"],
        *keymap.QUEUE_PAGE,
        Binding("q,escape,backspace", "go_back", "Back"),
        Binding("comma", "settings", "Settings"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._ids: list[str] = []
        self._shown: tuple[str, tuple[str, ...]] | None = None
        self._cursor_id: str | None = None
        self._removed: list[list[tuple[int, Entry]]] = []
        self._init_detail_focus()

    def compose(self) -> ComposeResult:
        with Horizontal(id="queue-main"):
            with Vertical(id="queue-center"):
                yield VideoListPanel(id="queue-video-list")
                yield Static(text("queue_screen.hint"), id="queue-hint", markup=True)
            yield DetailPanel(id="queue-detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_player_bar()
        self.call_after_refresh(self._rebuild)

    def _rebuild(self, focus_id: str | None = None) -> None:
        """Redraw when the queue or the playing track differs from what is shown, keeping the cursor's row or place."""
        audio = self.app.audio
        playing = audio.entry
        if playing is None:
            self._removed.clear()  # stopped: nothing to put a removed track back into
        rows = ([playing] if playing else []) + list(audio.queue)
        shown = ((playing or {}).get("id", ""), tuple(e.get("id", "") for e in audio.queue))
        if shown == self._shown and focus_id is None:
            return
        previous, self._shown = self._ids, shown
        self._ids = [e.get("id", "") for e in rows]
        count = len(audio.queue)
        panel = self._list()
        panel.set_breadcrumb(
            text("queue_screen.title_count", count=count) if count else text("queue_screen.title")
        )
        panel.set_playing((playing or {}).get("id"))
        wanted = focus_id or self._cursor_id
        if wanted not in self._ids:
            here = previous.index(self._cursor_id) if self._cursor_id in previous else 0
            wanted = self._ids[min(here, len(self._ids) - 1)] if self._ids else None
        self._cursor_id = wanted
        panel.replace_entries(rows, focus_id=wanted)
        if rows:
            panel.focus_list()
        else:
            panel.set_empty_message(text("queue_screen.empty"))
            self._cancel_pending_focus_and_thumb()
            self._detail().clear()

    def on_video_list_panel_selected(self, message: VideoListPanel.Selected) -> None:
        self._cursor_id = message.entry.get("id")
        self._focus_video(message.entry)

    def on_audio_queue_changed(self, _message: AudioQueueChanged) -> None:
        self._rebuild()

    def on_audio_track_changed(self, _message: AudioTrackChanged) -> None:
        self._rebuild()

    def on_player_state_updated(self, message: PlayerStateUpdated) -> None:
        if not message.playing:
            self._rebuild()

    def _on_page_shown(self) -> None:
        """The queue is held whole: turning a page loads nothing."""

    def _on_past_last_page(self) -> None:
        """The queue is held whole: there is nothing after the last page."""

    def _crumbs(self) -> list[str]:
        return [text("queue_screen.title")]

    def panel_hints(self) -> list[tuple[str, str]]:
        return [(b.key, text(f"queue_screen.key_{b.action}")) for b in keymap.QUEUE_PAGE]

    def _queue_index(self) -> int | None:
        """The highlighted row's position in the controller's queue; None on the playing track or with no row."""
        entry = self._selected_entry()
        queued = [e.get("id") for e in self.app.audio.queue]
        return queued.index(entry["id"]) if entry and entry.get("id") in queued else None

    def action_activate(self) -> None:
        index = self._queue_index()
        if index is None:
            if self._selected_entry():
                self._hint(text("queue_screen.already_playing"), "information")
            return
        self.app.audio.play_queued(index)
        self._rebuild()

    def action_queue_move_down(self) -> None:
        self._move(1)

    def action_queue_move_up(self) -> None:
        self._move(-1)

    def _move(self, step: int) -> None:
        index = self._queue_index()
        if index is None:
            return
        vid = self.app.audio.queue[index].get("id")
        if self.app.audio.move_queued(index, step) != index:
            self._rebuild(focus_id=vid)

    def action_queue_remove(self) -> None:
        index = self._queue_index()
        if index is None:
            if self._selected_entry():
                self._hint(text("queue_screen.is_playing"), "information")
            return
        removed = self.app.audio.remove_queued(index)
        if removed:
            self._removed.append([(index, removed)])
            self._rebuild()

    def action_queue_clear(self) -> None:
        cleared = self.app.audio.clear_queue()
        if not cleared:
            self._hint(text("item_actions.queue_empty"), "information")
            return
        self._removed.append(list(enumerate(cleared)))
        self._rebuild()

    def action_queue_undo(self) -> None:
        if not self._removed:
            self._hint(text("queue_screen.nothing_to_undo"), "information")
            return
        records = self._removed.pop()
        for index, entry in records:
            self.app.audio.insert_queued(index, entry)
        self._rebuild(focus_id=records[0][1].get("id"))

    def action_go_back(self) -> None:
        self.app.pop_screen()
