"""TermTube v2 — SearchModal.

Floating search dialog. Shows a text input and recent search history.
Emits a SearchRequested message with the query string when the user
confirms.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static


class SearchModal(ModalScreen[str | None]):
    """Search input with recent query history."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
    ]

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }
    #search-box {
        width: 70;
        max-width: 90%;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #search-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #search-input {
        margin-bottom: 1;
    }
    #search-history-label {
        color: $text-muted;
        margin-bottom: 0;
    }
    #search-history {
        height: 6;
        border: solid $surface-lighten-1;
        margin-bottom: 1;
    }
    #search-buttons {
        height: 3;
        layout: horizontal;
        align: right middle;
    }
    #search-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, recent_queries: list[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._recent = recent_queries or []

    def compose(self) -> ComposeResult:
        with Static(id="search-box"):
            yield Static("🔍  Search YouTube", id="search-title")
            yield Input(placeholder="Enter search query…", id="search-input")
            if self._recent:
                yield Static("Recent searches:", id="search-history-label")
                lv = ListView(id="search-history")
                yield lv
            with Static(id="search-buttons"):
                yield Button("Cancel", variant="default", id="search-cancel")
                yield Button("Search", variant="primary", id="search-go")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()
        try:
            lv = self.query_one("#search-history", ListView)
            for q in self._recent[:8]:
                lv.append(ListItem(Label(q)))
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-go":
            inp = self.query_one("#search-input", Input)
            self._submit(inp.value.strip())
        elif event.button.id == "search-cancel":
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        try:
            label = event.item.query_one(Label)
            query = str(label.renderable).strip()
            inp = self.query_one("#search-input", Input)
            inp.value = query
            inp.focus()
        except Exception:
            pass

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _submit(self, query: str) -> None:
        if query:
            self.dismiss(query)
        else:
            self.query_one("#search-input", Input).focus()
