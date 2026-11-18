from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from src import innertube, search_history

_MAX_ROWS = 8
_MIN_SUGGEST_CHARS = 2
_DEBOUNCE_S = 0.25


class SearchModal(ModalScreen[str | None]):
    """Search prompt with a list of earlier queries under it. Returns the query or None.

    Up/Down move through the list, Enter submits the highlighted row (or the typed text when none is
    highlighted), Ctrl+D forgets the highlighted query. Typing narrows the list, and (``search_suggestions``)
    after a 250 ms pause adds suggestions from Google below the matching history rows.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("ctrl+d", "forget", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._local: list[str] = []
        self._remote: list[str] = []
        self._candidates: list[str] = []
        self._selected: int | None = None
        self._seq = 0
        self._debounce = None

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
        self._schedule_suggestions(event.value.strip())
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
        self._local = search_history.matching(typed)[:_MAX_ROWS] if enabled else []
        self._merge()

    def _merge(self, keep: str | None = None) -> None:
        """History rows first, then suggestions not already listed; ``keep`` stays highlighted if still shown."""
        seen = {t.casefold() for t in self._local}
        extra = [t for t in self._remote if t.casefold() not in seen]
        self._candidates = (self._local + extra)[:_MAX_ROWS]
        self._selected = self._candidates.index(keep) if keep in self._candidates else None
        self._render_rows()

    def _schedule_suggestions(self, typed: str) -> None:
        """Ask for suggestions once typing pauses; any newer keystroke makes an answer in flight stale."""
        self._seq += 1
        if self._debounce is not None:
            self._debounce.stop()
            self._debounce = None
        if not self.app.config.search_suggestions_enabled or len(typed) < _MIN_SUGGEST_CHARS:  # type: ignore[attr-defined]
            self._remote = []
            return
        seq = self._seq
        self._debounce = self.set_timer(_DEBOUNCE_S, lambda: self._fetch_suggestions(typed, seq))

    def _fetch_suggestions(self, typed: str, seq: int) -> None:
        def work() -> None:
            try:
                found = innertube.fetch_suggestions(typed)
            except Exception:
                return
            self.app.call_from_thread(self._apply_suggestions, seq, found)

        self.run_worker(work, thread=True, exclusive=True, group="suggest")

    def _apply_suggestions(self, seq: int, found: list[str]) -> None:
        if seq != self._seq or not self.is_attached:
            return
        keep = self._candidates[self._selected] if self._selected is not None else None
        self._remote = found
        self._merge(keep)

    def _render_rows(self) -> None:
        local = len(self._local)
        lines = [
            ("[reverse] " if i == self._selected else "[dim] ")
            + ("🕐 " if i < local else "🔍 ")
            + escape(text) + " [/]"
            for i, text in enumerate(self._candidates)
        ]
        self.query_one("#search-suggestions", Static).update("\n".join(lines))
