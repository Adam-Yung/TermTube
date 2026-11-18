from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.strings import text

_PAGES = [
    ("1", "home", "nav_modal.page_home"),
    ("2", "subscriptions", "nav_modal.page_subscriptions"),
    ("3", "search", "nav_modal.page_search"),
    ("4", "history", "nav_modal.page_history"),
    ("5", "library", "nav_modal.page_library"),
    ("6", "help", "nav_modal.page_help"),
]


class NavModal(ModalScreen[str | None]):
    """Page picker opened by the backtick key. Returns the page id, or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("q", "cancel", "Cancel", show=False),
        *[Binding(num, f"pick('{page}')", show=False) for num, page, _ in _PAGES],
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="nav-dialog", classes="dialog"):
            yield Static(text("nav_modal.title"), id="nav-title", markup=True)
            for num, _page, label in _PAGES:
                yield Static(
                    f"[#ff4444]{num}[/#ff4444]  {text(label)}",
                    classes="nav-row",
                    markup=True,
                )
            yield Static(text("nav_modal.hint"), id="nav-hint", markup=True)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_pick(self, page: str) -> None:
        self.dismiss(page)
