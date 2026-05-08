"""TermTube v2 — ErrorModal.

Displayed whenever a non-fatal error should be surfaced to the user
(network failures, mpv errors, download errors, etc.).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ErrorModal(ModalScreen[None]):
    """Simple error dialog with title, message, and an OK button."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
    }
    #error-box {
        width: 60;
        max-width: 80%;
        height: auto;
        background: $surface;
        border: solid $error;
        padding: 1 2;
    }
    #error-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #error-msg {
        color: $text;
        margin-bottom: 2;
        height: auto;
    }
    #error-ok {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._err_title = title
        self._err_message = message

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                with Static(id="error-box"):
                    yield Static(f"⚠  {self._err_title}", id="error-title")
                    yield Static(self._err_message, id="error-msg")
                    yield Button("OK", variant="error", id="error-ok")

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss()
