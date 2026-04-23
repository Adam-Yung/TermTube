"""SearchModal — floating search input dialog."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class SearchModal(ModalScreen[str | None]):
    """Modal dialog for entering a search query. Returns the query or None."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Static("🔍  Search YouTube", id="search-title", markup=True)
            yield Input(
                placeholder="Type to search…",
                id="search-input",
            )
            yield Static(
                "[dim]Enter[/dim] to search  ·  [dim]Esc[/dim] to cancel",
                id="search-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self.dismiss(query)
        else:
            self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
