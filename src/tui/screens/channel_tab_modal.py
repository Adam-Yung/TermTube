from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.tui.widgets.action_bar import THEME_COLORS

_TABS = [
    ("1", "ch-tab-videos", "📼  Videos"),
    ("2", "ch-tab-playlists", "🎵  Playlists"),
]


class ChannelTabModal(ModalScreen[str | None]):
    """Popup tab picker for the channel screen. Returns tab id or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("1,v", "pick('ch-tab-videos')", show=False),
        Binding("2,p", "pick('ch-tab-playlists')", show=False),
    ]

    def __init__(self, current_tab: str = "ch-tab-videos") -> None:
        super().__init__()
        self._current_tab = current_tab

    def compose(self) -> ComposeResult:
        color = THEME_COLORS.get(self.app.config.theme, "#ff6666")
        with Vertical(id="ch-tab-dialog"):
            yield Static("Go to…", id="ch-tab-title", markup=True)
            for num, tab_id, label in _TABS:
                marker = " ✓" if tab_id == self._current_tab else ""
                yield Static(
                    f"[{color}]{num}[/{color}]  {label}[dim]{marker}[/dim]",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="ch-tab-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick(self, tab_id: str) -> None:
        self.dismiss(tab_id)
