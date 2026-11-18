from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from src.entries import Entry
from src.strings import text
from src.tui.fmt import fmt_duration
from src.tui.messages import AudioQueueChanged, AudioTrackChanged, PlayerStateUpdated


def _label(prefix: str, entry: Entry) -> Text:
    who = entry.get("uploader") or entry.get("channel") or ""
    length = fmt_duration(entry.get("duration"))
    label = Text(f"{prefix} {entry.get('title') or text('queue_modal.untitled')}")
    if who or length:
        label.append("  " + "  ·  ".join(p for p in (who, length) if p), style="dim")
    return label


class QueueModal(ModalScreen[None]):
    """The audio queue: the playing track on top, then the upcoming ones. Edits go through ``app.audio``.

    The playing track is shown but cannot be moved or removed (``>`` skips it, ``x`` stops audio).
    The list follows the controller's broadcasts, so it stays right while tracks advance behind it.
    """

    BINDINGS = [
        Binding("escape,q", "close", "Close", show=True),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("J", "move(1)", show=False),
        Binding("K", "move(-1)", show=False),
        Binding("D", "remove", show=False),
        Binding("u", "undo", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[str, Entry]] = []
        self._removed: list[tuple[int, Entry]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="queue-dialog", classes="dialog"):
            yield Static(text("queue_modal.title"), id="queue-title", markup=False)
            yield OptionList(id="queue-list", classes="dialog-list")
            yield Static(text("queue_modal.hint"), id="queue-hint", markup=True)

    def on_mount(self) -> None:
        self._rebuild()
        self._list.focus()

    @property
    def _list(self) -> OptionList:
        return self.query_one("#queue-list", OptionList)

    def _rebuild(self, focus_id: str | None = None) -> None:
        """Redraw from the controller, keeping the cursor on ``focus_id`` (or on the row it was on)."""
        audio = self.app.audio  # type: ignore[attr-defined]
        lv = self._list
        if focus_id is None and self._current_row():
            focus_id = self._current_row()[1].get("id")
        here = lv.highlighted or 0
        self._rows = []
        if audio.is_playing and audio.entry:
            self._rows.append(("now", audio.entry))
        self._rows += [("next", e) for e in audio.queue]
        lv.clear_options()
        if not self._rows:
            lv.add_option(Option(text("queue_modal.empty"), disabled=True))
        upcoming = 0
        for kind, entry in self._rows:
            upcoming += kind == "next"
            lv.add_option(Option(_label("▶" if kind == "now" else f"{upcoming}.", entry)))
        ids = [e.get("id") for _, e in self._rows]
        if self._rows:
            lv.highlighted = ids.index(focus_id) if focus_id in ids else min(here, len(self._rows) - 1)
        count = len(audio.queue)
        self.query_one("#queue-title", Static).update(
            text("queue_modal.title_count", count=count) if count else text("queue_modal.title")
        )

    def _current_row(self) -> tuple[str, Entry] | None:
        index = self._list.highlighted
        return self._rows[index] if index is not None and 0 <= index < len(self._rows) else None

    def _queue_index(self) -> int | None:
        """Position of the highlighted row in the controller's queue; None for the playing track or no row."""
        row, index = self._current_row(), self._list.highlighted
        if row is None or row[0] != "next":
            return None
        return index - (1 if self._rows[0][0] == "now" else 0)

    def on_audio_queue_changed(self, _message: AudioQueueChanged) -> None:
        self._rebuild()

    def on_audio_track_changed(self, _message: AudioTrackChanged) -> None:
        self._rebuild()

    def on_player_state_updated(self, message: PlayerStateUpdated) -> None:
        if not message.playing:
            self._rebuild()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        index = self._queue_index()
        if index is None:
            if self._current_row():
                self.notify(text("queue_modal.already_playing"), timeout=2)
            return
        self.app.audio.play_queued(index)  # type: ignore[attr-defined]
        self._rebuild()

    def action_move(self, step: int) -> None:
        index, row = self._queue_index(), self._current_row()
        if index is not None and row:
            self.app.audio.move_queued(index, step)  # type: ignore[attr-defined]
            self._rebuild(focus_id=row[1].get("id"))

    def action_remove(self) -> None:
        index, row = self._queue_index(), self._current_row()
        if index is None or row is None:
            if row:
                self.notify(text("queue_modal.is_playing"), timeout=3)
            return
        removed = self.app.audio.remove_queued(index)  # type: ignore[attr-defined]
        if removed:
            self._removed.append((index, removed))
            self._rebuild()

    def action_undo(self) -> None:
        if not self._removed:
            return
        index, entry = self._removed.pop()
        self.app.audio.insert_queued(index, entry)  # type: ignore[attr-defined]
        self._rebuild(focus_id=entry.get("id"))

    def action_cursor_down(self) -> None:
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._list.action_cursor_up()

    def action_close(self) -> None:
        self.dismiss(None)
