from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.tui.widgets.action_bar import THEME_COLORS

_ICONS = {"videos": "📼", "shorts": "📱", "live": "🔴", "playlists": "🎵"}
_DEFAULT_TABS = [("ch-tab-videos", "Videos"), ("ch-tab-playlists", "Playlists")]


class ChannelTabModal(ModalScreen[str | None]):
    """Popup tab picker for the channel screen: ``tabs`` are the ``(tab id, label)`` pairs the channel has.

    Returns the tab id or None.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        *[Binding(str(n), f"pick_nth({n})", show=False) for n in range(1, 5)],
        Binding("v", "pick('ch-tab-videos')", show=False),
        Binding("p", "pick('ch-tab-playlists')", show=False),
    ]

    def __init__(self, current_tab: str = "ch-tab-videos", tabs: list[tuple[str, str]] | None = None) -> None:
        super().__init__()
        self._current_tab = current_tab
        self._tabs = tabs or _DEFAULT_TABS

    def compose(self) -> ComposeResult:
        color = THEME_COLORS.get(self.app.config.theme, "#ff6666")
        with Vertical(id="ch-tab-dialog"):
            yield Static("Go to…", id="ch-tab-title", markup=True)
            for num, (tab_id, label) in enumerate(self._tabs, start=1):
                marker = " ✓" if tab_id == self._current_tab else ""
                icon = _ICONS.get(tab_id.removeprefix("ch-tab-"), "")
                yield Static(
                    f"[{color}]{num}[/{color}]  {icon}  {label}[dim]{marker}[/dim]",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="ch-tab-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick(self, tab_id: str) -> None:
        if any(tab_id == offered for offered, _ in self._tabs):
            self.dismiss(tab_id)

    def action_pick_nth(self, n: int) -> None:
        if n <= len(self._tabs):
            self.dismiss(self._tabs[n - 1][0])
