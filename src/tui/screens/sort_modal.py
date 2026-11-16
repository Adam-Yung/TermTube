from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.tui.widgets.action_bar import THEME_COLORS

_SORTS = [
    ("1", "date", "📅  Newest first"),
    ("2", "views", "👁  Most viewed"),
]


class SortModal(ModalScreen[str | None]):
    """Popup sort-order picker. Returns sort key or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("1,d", "pick('date')", show=False),
        Binding("2,v", "pick('views')", show=False),
    ]

    def __init__(self, current_sort: str = "date") -> None:
        super().__init__()
        self._current_sort = current_sort

    def compose(self) -> ComposeResult:
        color = THEME_COLORS.get(self.app.config.theme, "#ff6666")
        with Vertical(id="sort-dialog"):
            yield Static("Sort order", id="sort-title", markup=True)
            for num, key, label in _SORTS:
                marker = " ✓" if key == self._current_sort else ""
                yield Static(
                    f"[{color}]{num}[/{color}]  {label}[dim]{marker}[/dim]",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="sort-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick(self, sort: str) -> None:
        self.dismiss(sort)
