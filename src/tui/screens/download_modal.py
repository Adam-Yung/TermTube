"""DownloadModal -- shows live download progress inside the TUI."""

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
        self._error_msg: str = ""

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
                id="download-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._start_download()

    @work(thread=True, exclusive=True, group="download")
    def _start_download(self) -> None:
        import src.ytdlp as ytdlp
        app = self.app  # type: ignore[attr-defined]
        error_lines: list[str] = []

        def on_progress(line: str, pct: float) -> None:
            if self._cancelled:
                return
            if pct == ytdlp.PHASE_NEW_STREAM:
                self.app.call_from_thread(self._switch_to_audio_phase)
            elif pct == ytdlp.PHASE_POSTPROCESS:
                self.app.call_from_thread(self._switch_to_postprocess, line)
            elif pct >= 0:
                self.app.call_from_thread(self._update_progress, pct, line)
            # Capture error lines from yt-dlp output for display on failure
            stripped = line.strip()
            if stripped.startswith("ERROR:") or "error" in stripped.lower():
                error_lines.append(stripped[:120])

        try:
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
        except RuntimeError as exc:
            success = False
            error_lines.append(str(exc))
        except Exception as exc:
            success = False
            error_lines.append(f"Unexpected error: {exc}")

        if not self._cancelled:
            err = error_lines[-1] if error_lines else ""
            self.app.call_from_thread(self._on_done, success, err)

    def _switch_to_audio_phase(self) -> None:
        """Second stream detected -- reset bar and update title for audio download."""
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
        """Post-processing started -- switch to indeterminate state."""
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

    def _on_done(self, success: bool, error_msg: str = "") -> None:
        if success:
            try:
                bar = self.query_one("#download-bar", ProgressBar)
                bar.update(total=100, progress=100)
            except Exception:
                pass
            self.dismiss(True)
        else:
            # Show the error inline so the user knows what went wrong
            try:
                self.query_one("#download-title", Static).update(
                    "[bold red]\u26a0  Download failed[/bold red]"
                )
                msg = error_msg or "yt-dlp returned an error -- check cookies or network."
                self.query_one("#download-status", Static).update(
                    f"[red]{msg[:80]}[/red]"
                )
                self.query_one("#download-hint", Static).update(
                    "[dim]Press Esc to close[/dim]"
                )
                bar = self.query_one("#download-bar", ProgressBar)
                bar.update(total=100, progress=0)
            except Exception:
                pass
            self._error_msg = error_msg

    def action_cancel_download(self) -> None:
        self._cancelled = True
        self.dismiss(False)
