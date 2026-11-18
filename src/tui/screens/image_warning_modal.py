from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from src.strings import text


class ImageWarningModal(ModalScreen[bool]):
    """Startup notice for terminals without Kitty/Sixel. Dismisses with True for "never show again"."""

    BINDINGS = [Binding("escape", "ok", "OK", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="imgwarn-dialog", classes="dialog"):
            yield Static(text("image_warning_modal.title"), id="imgwarn-title", markup=True)
            yield Static(
                text("image_warning_modal.body"),
                id="imgwarn-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static(text("image_warning_modal.ok")), id="imgwarn-ok"),
                ListItem(Static(text("image_warning_modal.never")), id="imgwarn-never"),
                id="imgwarn-list",
            )

    def on_mount(self) -> None:
        self.query_one("#imgwarn-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.id == "imgwarn-never")

    def action_ok(self) -> None:
        self.dismiss(False)
