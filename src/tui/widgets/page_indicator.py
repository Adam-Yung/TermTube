"""PageIndicator — compact page navigation footer for the paged video list."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static


class PageIndicator(Widget):
    """Footer bar: ◀ | Page N / M | status | ▶"""

    DEFAULT_CSS = """
    PageIndicator {
        height: 1;
        layout: horizontal;
        dock: bottom;
    }
    PageIndicator #pi-prev {
        width: 3;
        min-width: 3;
        height: 1;
        background: transparent;
        border: none;
        color: $text-muted;
    }
    PageIndicator #pi-next {
        width: 3;
        min-width: 3;
        height: 1;
        background: transparent;
        border: none;
        color: $text-muted;
    }
    PageIndicator #pi-label {
        width: 1fr;
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    PageIndicator #pi-status {
        width: auto;
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    class PrevPage(Message):
        pass

    class NextPage(Message):
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current: int = 1
        self._total: int = 1
        self._next_ready: bool = False
        self._prefetching: bool = False

    def compose(self) -> ComposeResult:
        yield Button("◀", id="pi-prev", variant="default")
        yield Static("", id="pi-label", markup=True)
        yield Static("", id="pi-status", markup=True)
        yield Button("▶", id="pi-next", variant="default")

    def on_mount(self) -> None:
        self._render()

    def update_state(
        self,
        *,
        current: int | None = None,
        total: int | None = None,
        next_ready: bool | None = None,
        prefetching: bool | None = None,
    ) -> None:
        if current is not None:
            self._current = current
        if total is not None:
            self._total = total
        if next_ready is not None:
            self._next_ready = next_ready
        if prefetching is not None:
            self._prefetching = prefetching
        self._render()

    def _render(self) -> None:
        label = f"[dim]Page {self._current} / {self._total}[/dim]"
        try:
            self.query_one("#pi-label", Static).update(label)
        except Exception:
            return

        status = ""
        if self._prefetching and not self._next_ready:
            status = "[dim italic]loading next…[/dim italic]"
        try:
            self.query_one("#pi-status", Static).update(status)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "pi-prev":
            if self._current > 1:
                self.post_message(self.PrevPage())
        elif event.button.id == "pi-next":
            if self._next_ready:
                self.post_message(self.NextPage())
