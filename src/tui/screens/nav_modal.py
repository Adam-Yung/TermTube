"""NavModal — quick page-picker popup (backtick key)."""

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
    """
    Popup page-picker. Returns the tab id (str) of the selected page,
    or None if cancelled. Opened via the backtick key.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        Binding("1", "pick_home", show=False),
        Binding("2", "pick_subscriptions", show=False),
        Binding("3", "pick_search", show=False),
        Binding("4", "pick_history", show=False),
        Binding("5", "pick_library", show=False),
        Binding("6", "pick_playlists", show=False),
        Binding("7", "pick_help", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="nav-dialog"):
            yield Static("Go to page…", id="nav-title", markup=True)
            for num, _tab, label in _PAGES:
                yield Static(
                    f"[#ff4444]{num}[/#ff4444]  {label}",
                    classes="nav-row",
                    markup=True,
                )
            yield Static("[dim]press number or Esc[/dim]", id="nav-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick_home(self) -> None:
        self.dismiss("home")

    def action_pick_subscriptions(self) -> None:
        self.dismiss("subscriptions")

    def action_pick_search(self) -> None:
        self.dismiss("search")

    def action_pick_history(self) -> None:
        self.dismiss("history")

    def action_pick_library(self) -> None:
        self.dismiss("library")

    def action_pick_playlists(self) -> None:
        self.dismiss("playlists")

    def action_pick_help(self) -> None:
        self.dismiss("help")
