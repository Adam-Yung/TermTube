from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from src.tui.fmt import escape_markup


class NameModal(ModalScreen[str | None]):
    """One-line name prompt (playlist new / rename). Dismisses with the trimmed name, or None on Esc or empty."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, title: str, initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="playlist-dialog"):
            yield Static(f"🎵  {escape_markup(self._title)}", id="playlist-title", markup=True)
            yield Input(value=self._initial, placeholder="Name… (press Enter)", id="name-input")
            yield Static("[dim]Enter[/dim] save  ·  [dim]Esc[/dim] cancel", id="playlist-hint", markup=True)

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
