"""ChannelTabModal — tab picker popup for channel screen (backtick key)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_TABS = [
    ("1", "ch-tab-videos", "📼  Videos"),
    ("2", "ch-tab-playlists", "🎵  Playlists"),
]


class ChannelTabModal(ModalScreen[str | None]):
    """Popup tab picker for the channel screen. Returns tab id or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("1", "pick_videos", show=False),
        Binding("2", "pick_playlists", show=False),
        Binding("v", "pick_videos", show=False),
        Binding("p", "pick_playlists", show=False),
    ]

    DEFAULT_CSS = """
    ChannelTabModal {
        align: center middle;
    }
    #ch-tab-dialog {
        width: 36;
        height: auto;
        background: #1a1a1a;
        border: solid #444444;
        padding: 1 2;
    }
    #ch-tab-title {
        color: #ff4444;
        text-style: bold;
        margin-bottom: 1;
    }
    .ch-tab-row {
        height: 1;
        padding: 0 1;
    }
    #ch-tab-hint {
        margin-top: 1;
    }
    """

    def __init__(self, current_tab: str = "ch-tab-videos") -> None:
        super().__init__()
        self._current_tab = current_tab

    def compose(self) -> ComposeResult:
        with Vertical(id="ch-tab-dialog"):
            yield Static("Go to…", id="ch-tab-title", markup=True)
            for num, tab_id, label in _TABS:
                marker = " ✓" if tab_id == self._current_tab else ""
                yield Static(
                    f"[#ff4444]{num}[/#ff4444]  {label}[dim]{marker}[/dim]",
                    classes="ch-tab-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="ch-tab-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick_videos(self) -> None:
        self.dismiss("ch-tab-videos")

    def action_pick_playlists(self) -> None:
        self.dismiss("ch-tab-playlists")
