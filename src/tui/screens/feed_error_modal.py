"""FeedErrorModal — prompt to refresh cookies when a feed returns empty results."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class FeedErrorModal(ModalScreen[str]):
    """
    Shown when a feed returns no results and cookies are configured.
    Dismisses with "refresh", "update", or "skip".
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="feederror-dialog"):
            yield Static(
                "\u26a0  Feed returned no results",
                id="feederror-title",
                markup=True,
            )
            yield Static(
                "Cookies may be expired or invalid.\n"
                "Refreshing cookies or updating yt-dlp often fixes this.",
                id="feederror-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static("  Refresh cookies now"), id="feederror-refresh"),
                ListItem(Static("  Update yt-dlp"), id="feederror-update"),
                ListItem(Static("  Skip"), id="feederror-skip"),
                id="feederror-list",
            )

    def on_mount(self) -> None:
        self.query_one("#feederror-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or "feederror-skip"
        if item_id == "feederror-refresh":
            self.dismiss("refresh")
        elif item_id == "feederror-update":
            self.dismiss("update")
        else:
            self.dismiss("skip")

    def action_dismiss_modal(self) -> None:
        self.dismiss("skip")
