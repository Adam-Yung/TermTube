from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from src.strings import text

_SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class AppHeader(Widget):
    """Clock on the left, title in the centre, busy spinner on the right."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._frame = 0
        self._spinner_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-layout"):
            yield Static("", id="header-clock")
            yield Static(text("app_header.title"), id="header-title")
            yield Static("", id="header-status")

    def on_mount(self) -> None:
        self._update_clock()
        # The clock shows minutes only: wait for the next minute boundary, then tick every 60 s.
        self.set_timer(60 - datetime.now().second, self._start_minute_clock)

    def _start_minute_clock(self) -> None:
        self._update_clock()
        self.set_interval(60.0, self._update_clock)

    def _update_clock(self) -> None:
        now = datetime.now().strftime("%I:%M %p")
        self.query_one("#header-clock", Static).update(f"[dim]⌚ {now}[/dim]")

    def _animate_spinner(self) -> None:
        self._frame += 1
        self.query_one("#header-status", Static).update(_SPINNER[self._frame % len(_SPINNER)])

    def set_status_loading(self) -> None:
        if self._spinner_timer:
            return
        self._frame = 0
        self.query_one("#header-status", Static).update(_SPINNER[0])
        self._spinner_timer = self.set_interval(0.4, self._animate_spinner)

    def set_status_idle(self) -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self.query_one("#header-status", Static).update("")
