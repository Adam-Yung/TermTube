"""TermTube v2 — DownloadModal.

Progress overlay for video/audio downloads.
Stays open until the download completes or the user cancels.

Usage:
    await self.app.push_screen(DownloadModal(video_id, title, mode))
    # The modal cancels the download when dismissed early.
"""
from __future__ import annotations

import threading

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ProgressBar, Static


class DownloadModal(ModalScreen[bool]):
    """Download progress dialog for a single video or audio track."""

    BINDINGS = [
        Binding("escape", "cancel_download", "Cancel"),
    ]

    DEFAULT_CSS = """
    DownloadModal {
        align: center middle;
    }
    #dl-box {
        width: 64;
        max-width: 90%;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    #dl-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
        height: auto;
        overflow: hidden;
    }
    #dl-status {
        color: $text;
        margin-bottom: 1;
    }
    #dl-bar {
        margin-bottom: 1;
    }
    #dl-detail {
        color: $text-muted;
        margin-bottom: 1;
    }
    #dl-cancel {
        width: 100%;
    }
    """

    def __init__(
        self,
        video_id: str,
        title: str,
        mode: str = "video",
        **kwargs,
    ) -> None:
        """
        mode: 'video' | 'audio'
        The caller must start the download worker after pushing this screen.
        Use on_download_modal_mounted to know when it's safe to start.
        """
        super().__init__(**kwargs)
        self._video_id = video_id
        self._title = title
        self._mode = mode
        self._cancelled = False
        self.cancel_event = threading.Event()
        self._done = False

    def compose(self) -> ComposeResult:
        mode_label = "Video" if self._mode == "video" else "Audio"
        short = (self._title[:50] + "…") if len(self._title) > 50 else self._title
        with Static(id="dl-box"):
            yield Static(f"↓  Downloading {mode_label}", id="dl-title")
            yield Label(short, id="dl-status")
            yield ProgressBar(id="dl-bar", total=100, show_eta=False)
            yield Static("Starting…", id="dl-detail")
            yield Button("Cancel", variant="error", id="dl-cancel")

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.action_cancel_download()

    def action_cancel_download(self) -> None:
        if not self._done:
            self._cancelled = True
            self.cancel_event.set()
            self._update_status("Cancelling…")
            self.dismiss(False)

    # ------------------------------------------------------------------
    # Progress update API (called from download worker thread via
    # self.app.call_from_thread)
    # ------------------------------------------------------------------

    def on_progress(self, info: dict) -> None:
        """Called from the download worker with parsed progress dict."""
        if self._cancelled:
            return
        try:
            pct = info.get("percent", 0.0)
            speed = info.get("speed", "")
            eta = info.get("eta", "")
            bar = self.query_one("#dl-bar", ProgressBar)
            bar.progress = pct
            detail_parts = []
            if speed:
                detail_parts.append(speed)
            if eta:
                detail_parts.append(f"ETA {eta}")
            detail = "  ·  ".join(detail_parts) or "…"
            self._update_detail(detail)
        except Exception:
            pass

    def on_complete(self, success: bool) -> None:
        """Called from download worker when download finishes."""
        self._done = True
        if success:
            self._update_status("✓  Download complete")
            self._update_detail("")
            try:
                self.query_one("#dl-cancel", Button).label = "Close"
                self.query_one("#dl-cancel", Button).variant = "success"
            except Exception:
                pass
            self.set_timer(1.5, lambda: self.dismiss(True))
        else:
            self._update_status("✗  Download failed")
            self.dismiss(False)

    # ------------------------------------------------------------------

    def _update_status(self, text: str) -> None:
        try:
            self.query_one("#dl-status", Label).update(text)
        except Exception:
            pass

    def _update_detail(self, text: str) -> None:
        try:
            self.query_one("#dl-detail", Static).update(text)
        except Exception:
            pass
