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

    def __init__(self, video_id: str, entry: dict, audio_only: bool = False, fmt: str = "") -> None:
        super().__init__()
        self._video_id = video_id
        self._entry = entry
        self._audio_only = audio_only
        self._fmt = fmt
        self._cancelled = False
        self._phase = "video" if not audio_only else "audio"

    def compose(self) -> ComposeResult:
        title = self._entry.get("title", self._video_id)
        mode = "audio" if self._audio_only else "video"
        with Vertical(id="download-dialog"):
            yield Static(
                f"\u2b07  Downloading {mode}",
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
            if pct == ytdlp.PHASE_NEW_STREAM:
                self.app.call_from_thread(self._switch_to_audio_phase)
            elif pct == ytdlp.PHASE_POSTPROCESS:
                self.app.call_from_thread(self._switch_to_postprocess, line)
            elif pct >= 0:
                self.app.call_from_thread(self._update_progress, pct, line)

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
                quality_format=self._fmt,
                on_progress=on_progress,
            )

        if not self._cancelled:
            self.app.call_from_thread(self._on_done, success)

    def _switch_to_audio_phase(self) -> None:
        """Second stream detected — reset bar and update title for audio download."""
        self._phase = "audio"
        try:
            self.query_one("#download-title", Static).update(
                "\u2b07  Downloading audio"
            )
            bar = self.query_one("#download-bar", ProgressBar)
            bar.progress = 0
            self.query_one("#download-status", Static).update(
                "[dim]Downloading audio track...[/dim]"
            )
        except Exception:
            pass

    def _switch_to_postprocess(self, line: str) -> None:
        """Post-processing started — switch to indeterminate state."""
        self._phase = "postprocess"
        try:
            if "Merger" in line or "Merging" in line:
                label = "Merging video + audio..."
            elif "ExtractAudio" in line or "FFmpegExtractAudio" in line:
                label = "Converting audio..."
            else:
                label = "Processing..."
            self.query_one("#download-title", Static).update(
                f"\u2699  {label}"
            )
            bar = self.query_one("#download-bar", ProgressBar)
            bar.update(total=None, progress=0)
            self.query_one("#download-status", Static).update(
                "[dim]Please wait...[/dim]"
            )
        except Exception:
            pass

    def _update_progress(self, pct: float, line: str) -> None:
        try:
            bar = self.query_one("#download-bar", ProgressBar)
            if bar.total is None:
                bar.update(total=100, progress=pct)
            else:
                bar.update(progress=pct)
            clean = line.strip()
            if clean and not clean.startswith("[download]"):
                self.query_one("#download-status", Static).update(
                    f"[dim]{clean[:60]}[/dim]"
                )
            elif "[download]" in clean:
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
            bar.update(total=100, progress=100)
        except Exception:
            pass
        self.dismiss(success)

    def action_cancel_download(self) -> None:
        self._cancelled = True
        self.dismiss(False)
