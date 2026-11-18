from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from src import search_history

_MAX_ROWS = 8


class SearchModal(ModalScreen[str | None]):
    """Search prompt with a list of earlier queries under it. Returns the query or None.

    Up/Down move through the list, Enter submits the highlighted row (or the typed text when none is
    highlighted), Ctrl+D forgets the highlighted query. Typing narrows the list.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("ctrl+d", "forget", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._candidates: list[str] = []
        self._selected: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Static("🔍  Search YouTube", id="search-title", markup=True)
            yield Input(placeholder="Type to search…", id="search-input")
            yield Static("", id="search-suggestions", markup=True)
            yield Static(
                "[dim]Enter[/dim] search  ·  [dim]↑↓[/dim] history  ·  "
                "[dim]Ctrl+D[/dim] forget  ·  [dim]Esc[/dim] cancel",
                id="search-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()
        self._refresh("")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        typed = event.value.strip()
        if self._selected is not None:
            typed = self._candidates[self._selected]
        self.dismiss(typed or None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def action_move(self, step: int) -> None:
        if not self._candidates:
            return
        if self._selected is None:
            self._selected = 0 if step > 0 else len(self._candidates) - 1
        else:
            self._selected = (self._selected + step) % len(self._candidates)
        self._render_rows()

    def action_forget(self) -> None:
        if self._selected is None:
            return
        search_history.remove(self._candidates[self._selected])
        self._refresh(self.query_one("#search-input", Input).value)

    def _refresh(self, typed: str) -> None:
        enabled = self.app.config.search_history_enabled  # type: ignore[attr-defined]
        self._candidates = search_history.matching(typed)[:_MAX_ROWS] if enabled else []
        self._selected = None
        self._render_rows()

    def _render_rows(self) -> None:
        lines = [
            ("[reverse] " if i == self._selected else "[dim] ") + "🕐 " + escape(text) + " [/]"
            for i, text in enumerate(self._candidates)
        ]
        self.query_one("#search-suggestions", Static).update("\n".join(lines))
