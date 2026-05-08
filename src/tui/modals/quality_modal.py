"""TermTube v2 — QualityModal.

Lets the user pick a video or audio quality format string before playback
or download.  Returns (label, format_string) or None if cancelled.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ytdlp import AUDIO_QUALITY_CHOICES, QUALITY_CHOICES


class QualityModal(ModalScreen[tuple[str, str] | None]):
    """Quality picker for video or audio."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
    ]

    DEFAULT_CSS = """
    QualityModal {
        align: center middle;
    }
    #quality-box {
        width: 50;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #quality-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #quality-list {
        height: auto;
    }
    """

    def __init__(self, mode: str = "video", **kwargs) -> None:
        """mode: 'video' or 'audio'"""
        super().__init__(**kwargs)
        self._mode = mode
        self._choices = QUALITY_CHOICES if mode == "video" else AUDIO_QUALITY_CHOICES

    def compose(self) -> ComposeResult:
        title = "Video quality" if self._mode == "video" else "Audio quality"
        with Static(id="quality-box"):
            yield Static(title, id="quality-title")
            lv = ListView(id="quality-list")
            yield lv

    def on_mount(self) -> None:
        lv = self.query_one("#quality-list", ListView)
        for label, fmt in self._choices:
            item = ListItem(Label(label))
            item.data = (label, fmt)  # type: ignore[attr-defined]
            lv.append(item)
        lv.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        result = getattr(event.item, "data", None)
        self.dismiss(result)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
