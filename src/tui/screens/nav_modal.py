from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_PAGES = [
    ("1", "home", "🏠  Home"),
    ("2", "subscriptions", "📺  Subscriptions"),
    ("3", "search", "🔍  Search"),
    ("4", "history", "🕐  History"),
    ("5", "library", "📁  Library"),
    ("6", "playlists", "🎵  Playlists"),
    ("7", "help", "📚  Help"),
]


class NavModal(ModalScreen[str | None]):
    """Page picker opened by the backtick key. Returns the page id, or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        *[Binding(num, f"pick('{page}')", show=False) for num, page, _ in _PAGES],
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="nav-dialog"):
            yield Static("Go to page…", id="nav-title", markup=True)
            for num, _page, label in _PAGES:
                yield Static(
                    f"[#ff4444]{num}[/#ff4444]  {label}",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="nav-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick(self, page: str) -> None:
        self.dismiss(page)
