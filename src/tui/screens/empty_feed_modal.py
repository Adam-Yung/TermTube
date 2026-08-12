"""EmptyFeedModal — shown when the feed returns no videos."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class EmptyFeedModal(ModalScreen[str]):
    """
    Shown when a feed returns no results.
    Dismisses with "update", "settings", or "skip".
    """

    BINDINGS = [Binding("escape", "skip", "Skip", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="emptyfeed-dialog"):
            yield Static(
                "⚠  Feed returned no results",
                id="emptyfeed-title",
                markup=True,
            )
            yield Static(
                "This usually means browser authentication isn't working.\n"
                "Make sure you're logged into YouTube in your browser.",
                id="emptyfeed-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static("  Update yt-dlp"), id="emptyfeed-update"),
                ListItem(Static("  Open Settings"), id="emptyfeed-settings"),
                ListItem(Static("  Skip"), id="emptyfeed-skip"),
                id="emptyfeed-list",
            )

    def on_mount(self) -> None:
        self.query_one("#emptyfeed-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or "emptyfeed-skip"
        if item_id == "emptyfeed-update":
            self.dismiss("update")
        elif item_id == "emptyfeed-settings":
            self.dismiss("settings")
        else:
            self.dismiss("skip")

    def action_skip(self) -> None:
        self.dismiss("skip")
