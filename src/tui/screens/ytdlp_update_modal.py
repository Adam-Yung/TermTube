"""YtdlpUpdateModal — prompt to update yt-dlp when extraction errors occur."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class YtdlpUpdateModal(ModalScreen[str]):
    """
    Shown when feed loading fails with extraction errors.
    Dismisses with "update" or "skip".
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel", show=False)]

    def __init__(self, error_detail: str = "") -> None:
        super().__init__()
        self._error_detail = error_detail

    def compose(self) -> ComposeResult:
        with Vertical(id="ytdlp-update-dialog"):
            yield Static(
                "\u26a0  Video fetching error",
                id="ytdlp-update-title",
                markup=True,
            )
            body = (
                "yt-dlp may be outdated and unable to extract video data.\n"
                "Updating often fixes extraction errors."
            )
            if self._error_detail:
                body += f"\n\n[dim]{self._error_detail[:120]}[/dim]"
            yield Static(body, id="ytdlp-update-body", markup=True)
            yield ListView(
                ListItem(Static("  Update yt-dlp now"), id="ytdlp-update-yes"),
                ListItem(Static("  Skip"), id="ytdlp-update-skip"),
                id="ytdlp-update-list",
            )

    def on_mount(self) -> None:
        self.query_one("#ytdlp-update-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or "ytdlp-update-skip"
        if item_id == "ytdlp-update-yes":
            self.dismiss("update")
        else:
            self.dismiss("skip")

    def action_dismiss_modal(self) -> None:
        self.dismiss("skip")
