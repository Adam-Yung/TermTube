"""CookieWarningModal — one-time startup notice when no cookies.txt is present."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class CookieWarningModal(ModalScreen[str]):
    """
    Shown once at startup when no cookies.txt file exists.
    Dismisses with the selected item's id string.
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="cookiewarn-dialog"):
            yield Static("⚠  No Cookies Present", id="cookiewarn-title", markup=True)
            yield Static(
                "TermTube uses your browser's cookies to authenticate with YouTube.\n"
                "Without cookies, the Home and Subscriptions feeds cannot load\n"
                "personalized content.\n\n"
                "To set up cookies, run this command in your terminal:\n"
                "  termtube --refresh-cookies",
                id="cookiewarn-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static("  Run cookie refresh now"), id="cookiewarn-now"),
                ListItem(Static("  Run after TermTube exits"), id="cookiewarn-exit"),
                ListItem(Static("  Never show this warning"), id="cookiewarn-never"),
                id="cookiewarn-list",
            )

    def on_mount(self) -> None:
        self.query_one("#cookiewarn-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.id or "cookiewarn-never")

    def action_dismiss_modal(self) -> None:
        self.dismiss("cookiewarn-never")
