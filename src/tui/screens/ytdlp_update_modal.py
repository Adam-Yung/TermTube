from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.strings import text
from src.tui.fmt import escape_markup


class YtdlpUpdateModal(ModalScreen[str]):
    """Shown on feed extraction errors. Dismisses with "update" or "skip"."""

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel", show=False)]

    def __init__(self, error_detail: str = "") -> None:
        super().__init__()
        self._error_detail = error_detail

    def compose(self) -> ComposeResult:
        with Vertical(id="ytdlp-update-dialog", classes="dialog"):
            yield Static(
                text("ytdlp_update_modal.title"),
                id="ytdlp-update-title",
                markup=True,
            )
            body = text("ytdlp_update_modal.body")
            if self._error_detail:
                body += text("ytdlp_update_modal.detail", detail=escape_markup(self._error_detail[:120]))
            yield Static(body, id="ytdlp-update-body", markup=True)
            yield ListView(
                ListItem(Static(text("ytdlp_update_modal.update")), id="ytdlp-update-yes"),
                ListItem(Static(text("ytdlp_update_modal.skip")), id="ytdlp-update-skip"),
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
