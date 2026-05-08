"""TermTube v2 — PlaylistModal.

Lets the user pick an existing playlist to add a video to, or create a
new one.  Returns the chosen playlist name or None if cancelled.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

import playlist as _playlist


class PlaylistModal(ModalScreen[str | None]):
    """Add-to-playlist dialog."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
    ]

    DEFAULT_CSS = """
    PlaylistModal {
        align: center middle;
    }
    #pl-box {
        width: 52;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #pl-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #pl-list {
        height: 8;
        border: solid $surface-lighten-1;
        margin-bottom: 1;
    }
    #pl-new-label {
        color: $text-muted;
        margin-bottom: 0;
    }
    #pl-new-input {
        margin-bottom: 1;
    }
    #pl-buttons {
        height: 3;
        layout: horizontal;
        align: right middle;
    }
    #pl-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, video_id: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._video_id = video_id

    def compose(self) -> ComposeResult:
        with Static(id="pl-box"):
            yield Static("♬  Add to playlist", id="pl-title")
            yield ListView(id="pl-list")
            yield Static("Create new playlist:", id="pl-new-label")
            yield Input(placeholder="New playlist name…", id="pl-new-input")
            with Static(id="pl-buttons"):
                yield Button("Cancel", variant="default", id="pl-cancel")
                yield Button("Add", variant="primary", id="pl-add")

    def on_mount(self) -> None:
        lv = self.query_one("#pl-list", ListView)
        names = _playlist.list_names()
        for name in names:
            item = ListItem(Label(name))
            item.data = name  # type: ignore[attr-defined]
            lv.append(item)
        if names:
            lv.focus()
        else:
            self.query_one("#pl-new-input", Input).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = getattr(event.item, "data", None)
        if name:
            self.dismiss(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pl-add":
            inp = self.query_one("#pl-new-input", Input)
            name = inp.value.strip()
            if name:
                _playlist.create(name, [])
                self.dismiss(name)
            else:
                inp.focus()
        elif event.button.id == "pl-cancel":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            _playlist.create(name, [])
            self.dismiss(name)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
