"""ImageWarningModal — one-time startup notice when Kitty/Sixel image rendering is unavailable."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class ImageWarningModal(ModalScreen[bool]):
    """
    Shown once at startup when the terminal lacks Kitty/Sixel graphics support.
    Dismisses with False (OK) or True (never show again).
    """

    BINDINGS = [Binding("escape", "ok", "OK", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="imgwarn-dialog"):
            yield Static("⚠  No image protocol support", id="imgwarn-title", markup=True)
            yield Static(
                "Your terminal or tmux config doesn't support Kitty or\n"
                "Sixel graphics. Thumbnails will use ANSI block art instead.\n\n"
                "For native image rendering, use [bold]Kitty[/bold], [bold]WezTerm[/bold],\n"
                "or [bold]iTerm2[/bold] — and launch TermTube outside of tmux.",
                id="imgwarn-body",
                markup=True,
            )
            yield ListView(
                ListItem(Static("  OK"), id="imgwarn-ok"),
                ListItem(Static("  Never show again"), id="imgwarn-never"),
                id="imgwarn-list",
            )

    def on_mount(self) -> None:
        self.query_one("#imgwarn-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(event.item.id == "imgwarn-never")

    def action_ok(self) -> None:
        self.dismiss(False)
