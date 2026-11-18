from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.strings import text


class EmptyFeedModal(ModalScreen[str]):
    """Shown when a feed returns no results. Dismisses with "update", "refresh", "settings" or "skip"."""

    BINDINGS = [Binding("escape", "skip", "Skip", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="emptyfeed-dialog", classes="dialog"):
            yield Static(
                text("empty_feed_modal.title"),
                id="emptyfeed-title",
                markup=True,
            )
            yield Static(
                text("empty_feed_modal.body"),
                id="emptyfeed-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static(text("empty_feed_modal.update")), id="emptyfeed-update"),
                ListItem(Static(text("empty_feed_modal.refresh")), id="emptyfeed-refresh"),
                ListItem(Static(text("empty_feed_modal.settings")), id="emptyfeed-settings"),
                ListItem(Static(text("empty_feed_modal.skip")), id="emptyfeed-skip"),
                id="emptyfeed-list",
            )

    def on_mount(self) -> None:
        self.query_one("#emptyfeed-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or "emptyfeed-skip"
        if item_id == "emptyfeed-update":
            self.dismiss("update")
        elif item_id == "emptyfeed-refresh":
            self.dismiss("refresh")
        elif item_id == "emptyfeed-settings":
            self.dismiss("settings")
        else:
            self.dismiss("skip")

    def action_skip(self) -> None:
        self.dismiss("skip")
