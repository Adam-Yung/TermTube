from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.tui.widgets.action_bar import THEME_COLORS

CHANNEL_SORTS: list[tuple[str, str, str]] = [
    ("date", "📅  Newest first", "d"),
    ("views", "👁  Most viewed", "v"),
]
"""Option rows: ``(key returned, label, letter shortcut)``. The row number is its position."""


class SortModal(ModalScreen[str | None]):
    """Popup picker for a sort order or a result type. Returns the chosen key, or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        current_sort: str = "date",
        *,
        options: list[tuple[str, str, str]] | None = None,
        title: str = "Sort order",
    ) -> None:
        super().__init__()
        self._current_sort = current_sort
        self._options = options or CHANNEL_SORTS
        self._title = title

    def compose(self) -> ComposeResult:
        color = THEME_COLORS.get(self.app.config.theme, "#ff6666")
        with Vertical(id="sort-dialog", classes="dialog"):
            yield Static(self._title, id="sort-title", markup=True)
            for num, (key, label, _) in enumerate(self._options, 1):
                marker = " ✓" if key == self._current_sort else ""
                yield Static(
                    f"[{color}]{num}[/{color}]  {label}[dim]{marker}[/dim]",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="sort-hint", markup=True)

    def on_key(self, event: events.Key) -> None:
        for num, (key, _, letter) in enumerate(self._options, 1):
            if event.key in (str(num), letter):
                event.stop()
                self.dismiss(key)
                return

    def action_cancel(self) -> None:
        self.dismiss(None)
