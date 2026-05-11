"""SortModal — sort order picker popup for channel videos."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_SORTS = [
    ("1", "date", "📅  Newest first"),
    ("2", "views", "👁  Most viewed"),
]


class SortModal(ModalScreen[str | None]):
    """Popup sort-order picker. Returns sort key or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("1", "pick_date", show=False),
        Binding("2", "pick_views", show=False),
        Binding("d", "pick_date", show=False),
        Binding("v", "pick_views", show=False),
    ]

    DEFAULT_CSS = """
    SortModal {
        align: center middle;
    }
    #sort-dialog {
        width: 40;
        height: auto;
        background: #1a1a1a;
        border: solid #444444;
        padding: 1 2;
    }
    #sort-title {
        color: #ff4444;
        text-style: bold;
        margin-bottom: 1;
    }
    .sort-row {
        height: 1;
        padding: 0 1;
    }
    #sort-hint {
        margin-top: 1;
    }
    """

    def __init__(self, current_sort: str = "date") -> None:
        super().__init__()
        self._current_sort = current_sort

    def compose(self) -> ComposeResult:
        with Vertical(id="sort-dialog"):
            yield Static("Sort order", id="sort-title", markup=True)
            for num, key, label in _SORTS:
                marker = " ✓" if key == self._current_sort else ""
                yield Static(
                    f"[#ff4444]{num}[/#ff4444]  {label}[dim]{marker}[/dim]",
                    classes="sort-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="sort-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick_date(self) -> None:
        self.dismiss("date")

    def action_pick_views(self) -> None:
        self.dismiss("views")
