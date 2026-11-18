from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.downloads import AUDIO_QUALITY_CHOICES, QUALITY_CHOICES


class _QualityItem(ListItem):
    def __init__(self, label: str, fmt: str) -> None:
        super().__init__()
        self.fmt = fmt
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label, markup=False)


class QualityModal(ModalScreen[str | None]):
    """Choose a quality/format. Returns the yt-dlp format string or None on cancel.

    ``choices`` (``(label, value)`` rows) with a ``title`` makes it a plain picker: Settings uses it for every
    multiple-choice setting, and ``current`` marks the active value and starts the cursor on it.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=True),
        Binding("j",      "cursor_down",  show=False),
        Binding("k",      "cursor_up",    show=False),
    ]

    def __init__(
        self,
        *,
        audio_only: bool = False,
        choices: list[tuple[str, str]] | None = None,
        title: str | None = None,
        current: str | None = None,
    ) -> None:
        super().__init__()
        self._choices = choices or (AUDIO_QUALITY_CHOICES if audio_only else QUALITY_CHOICES)
        self._title = title or f"Select {'audio' if audio_only else 'video'} quality"
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="quality-dialog"):
            yield Static(self._title, id="quality-title", markup=False)
            yield ListView(id="quality-list")
            yield Static(
                "[dim]Enter[/dim] select  ·  [dim]Esc[/dim] cancel",
                id="quality-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        lv = self.query_one("#quality-list", ListView)
        for label, fmt in self._choices:
            marker = "" if self._current is None else ("▶ " if fmt == self._current else "  ")
            lv.append(_QualityItem(marker + label, fmt))
        lv.focus()
        values = [fmt for _, fmt in self._choices]
        lv.index = values.index(self._current) if self._current in values else 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, _QualityItem):
            self.dismiss(event.item.fmt)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one("#quality-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#quality-list", ListView).action_cursor_up()
