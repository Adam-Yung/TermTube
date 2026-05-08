"""TermTube v2 — NotificationBar.

An ephemeral single-line toast bar docked inside the VideoListPanel area.
Appears for a configurable duration then fades back to empty.

Usage (from main thread or via call_from_thread):
    self.query_one("#notify-bar", NotificationBar).show("Video hidden", kind="info")
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


_KIND_STYLES: dict[str, str] = {
    "info":    "bold white",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "skip":    "bold cyan",        # SponsorBlock skip
}

_KIND_ICONS: dict[str, str] = {
    "info":    "ℹ",
    "success": "✓",
    "warning": "⚠",
    "error":   "✗",
    "skip":    "⏭",
}


class NotificationBar(Widget):
    """Ephemeral status toast — auto-clears after `duration` seconds."""

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
    """

    def __init__(self, duration: float = 3.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._duration = duration
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static("", id="notify-text")

    def show(self, message: str, *, kind: str = "info", duration: float | None = None) -> None:
        """Display *message* for *duration* seconds then auto-hide."""
        icon = _KIND_ICONS.get(kind, "ℹ")
        style = _KIND_STYLES.get(kind, "bold white")
        try:
            self.query_one("#notify-text", Static).update(
                f"[{style}]{icon}  {message}[/{style}]"
            )
        except Exception:
            return

        self.add_class("--visible")

        # Cancel any pending auto-hide
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass

        secs = duration if duration is not None else self._duration
        self._timer = self.set_timer(secs, self._hide)

    def _hide(self) -> None:
        self.remove_class("--visible")
        try:
            self.query_one("#notify-text", Static).update("")
        except Exception:
            pass
