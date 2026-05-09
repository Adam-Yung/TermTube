"""TermTube v2 — NotificationBar.

A toast bar docked above the MiniPlayer.

Two modes:
  - Ephemeral (info/success/skip): auto-dismiss after configurable duration.
  - Persistent (error/warning): stays until user presses Esc. Pressing E opens
    the ErrorModal with full details.

Usage (from main thread or via call_from_thread):
    bar = self.query_one("#notify-bar", NotificationBar)
    bar.show("Video hidden", kind="info")
    bar.show("Playback failed: codec error", kind="error", persistent=True, detail="full error msg")
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


_KIND_STYLES: dict[str, str] = {
    "info":    "bold white",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "skip":    "bold cyan",
}

_KIND_ICONS: dict[str, str] = {
    "info":    "ℹ",
    "success": "✓",
    "warning": "⚠",
    "error":   "✗",
    "skip":    "⏭",
}


class NotificationBar(Widget):
    """Toast bar — ephemeral or persistent error notifications."""

    BINDINGS = [
        Binding("escape", "dismiss_notification", "Dismiss", show=False),
    ]

    class OpenErrorRequested(Message):
        """Posted when user presses E on a persistent error toast."""
        def __init__(self, title: str, detail: str) -> None:
            super().__init__()
            self.title = title
            self.detail = detail

    DEFAULT_CSS = """
    NotificationBar {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
        color: $text-muted;
        display: none;
    }
    NotificationBar.--visible {
        display: block;
    }
    NotificationBar.--persistent {
        background: $error 20%;
    }
    """

    def __init__(self, duration: float = 3.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._duration = duration
        self._timer = None
        self._persistent = False
        self._error_title = ""
        self._error_detail = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="notify-text")

    def show(
        self,
        message: str,
        *,
        kind: str = "info",
        duration: float | None = None,
        persistent: bool = False,
        detail: str = "",
    ) -> None:
        """Display *message*. Persistent errors stay until Esc."""
        icon = _KIND_ICONS.get(kind, "ℹ")
        style = _KIND_STYLES.get(kind, "bold white")

        suffix = ""
        if persistent:
            suffix = "  [dim](Esc dismiss · E details)[/dim]"

        try:
            self.query_one("#notify-text", Static).update(
                f"[{style}]{icon}  {message}[/{style}]{suffix}"
            )
        except Exception:
            return

        self._persistent = persistent
        self._error_title = message if persistent else ""
        self._error_detail = detail if persistent else ""

        self.add_class("--visible")
        if persistent:
            self.add_class("--persistent")
        else:
            self.remove_class("--persistent")

        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None

        if not persistent:
            secs = duration if duration is not None else self._duration
            self._timer = self.set_timer(secs, self._hide)

    def show_error(self, message: str, detail: str = "") -> None:
        """Convenience: show a persistent error."""
        self.show(message, kind="error", persistent=True, detail=detail)

    def action_dismiss_notification(self) -> None:
        self._hide()

    def on_key(self, event) -> None:
        if event.key == "E" and self._persistent and self._error_detail:
            self.post_message(self.OpenErrorRequested(self._error_title, self._error_detail))
            event.stop()

    def _hide(self) -> None:
        self._persistent = False
        self._error_title = ""
        self._error_detail = ""
        self.remove_class("--visible")
        self.remove_class("--persistent")
        try:
            self.query_one("#notify-text", Static).update("")
        except Exception:
            pass
