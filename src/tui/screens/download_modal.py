"""DownloadModal — shows live download progress inside the TUI."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static


class DownloadModal(ModalScreen[bool]):
    """Modal dialog showing yt-dlp download progress. Returns True on success."""

    BINDINGS = [
        Binding("escape", "cancel_download", "Cancel", show=True),
    ]

    def __init__(self, video_id: str, entry: dict, audio_only: bool = False) -> None:
        super().__init__()
        self._video_id = video_id
        self._entry = entry
        self._audio_only = audio_only
        self._cancelled = False

    def compose(self) -> ComposeResult:
        title = self._entry.get("title", self._video_id)
        mode = "audio" if self._audio_only else "video"
        with Vertical(id="download-dialog"):
            yield Static(
                f"⬇  Downloading {mode}",
                id="download-title",
                markup=True,
            )
            yield Static(
                f"[dim]{title[:60]}[/dim]",
                id="download-status",
                markup=True,
            )
            yield ProgressBar(total=100, show_eta=False, id="download-bar")
            yield Static(
                "[dim]Esc[/dim] to cancel",
                markup=True,
            )

    def on_mount(self) -> None:
        self._start_download()

    @work(thread=True, exclusive=True, group="download")
    def _start_download(self) -> None:
        import src.ytdlp as ytdlp
        app = self.app  # type: ignore[attr-defined]

        def on_progress(line: str, pct: float) -> None:
            if self._cancelled:
                return
            if pct >= 0:
                self.call_from_thread(self._update_progress, pct, line)

        if self._audio_only:
            success = ytdlp.download_audio_with_progress(
                self._video_id,
                app.config,
                on_progress=on_progress,
            )
        else:
            success = ytdlp.download_video_with_progress(
                self._video_id,
                app.config,
                on_progress=on_progress,
            )

        if not self._cancelled:
            self.call_from_thread(self._on_done, success)

    def _update_progress(self, pct: float, line: str) -> None:
        try:
            bar = self.query_one("#download-bar", ProgressBar)
            bar.progress = pct
            # Show last meaningful status line
            clean = line.strip()
            if clean and not clean.startswith("[download]"):
                self.query_one("#download-status", Static).update(
                    f"[dim]{clean[:60]}[/dim]"
                )
            elif "[download]" in clean:
                # extract speed/ETA from the progress line
                parts = clean.replace("[download]", "").strip()
                if parts:
                    self.query_one("#download-status", Static).update(
                        f"[dim]{parts[:60]}[/dim]"
                    )
        except Exception:
            pass

    def _on_done(self, success: bool) -> None:
        try:
            bar = self.query_one("#download-bar", ProgressBar)
            bar.progress = 100
        except Exception:
            pass
        self.dismiss(success)

    def action_cancel_download(self) -> None:
        self._cancelled = True
        self.dismiss(False)
