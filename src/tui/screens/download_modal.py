from __future__ import annotations

import threading

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static

from src import library
from src.entries import Entry
from src.tui.fmt import escape_markup


class DownloadModal(ModalScreen[bool]):
    """Modal dialog showing yt-dlp download progress. Returns True on success."""

    BINDINGS = [
        Binding("escape", "cancel_download", "Cancel", show=True),
        Binding("space", "audio_pause", show=False),
        Binding("x", "audio_stop", show=False),
    ]

    def __init__(self, video_id: str, entry: Entry, audio_only: bool = False, fmt: str = "") -> None:
        super().__init__()
        self._video_id = video_id
        self._entry = entry
        self._audio_only = audio_only
        self._fmt = fmt
        self._cancelled = False
        self._cancel_event: threading.Event | None = None

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
                f"[dim]{escape_markup(title[:60])}[/dim]",
                id="download-status",
                markup=True,
            )
            yield ProgressBar(total=100, show_eta=False, id="download-bar")
            audio = "  [dim]Space[/dim] pause audio  [dim]x[/dim] stop audio" if self.app.audio.is_playing else ""
            yield Static(
                f"[dim]Esc[/dim] to cancel{audio}",
                id="download-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        from src.ytdlp import new_cancel_event

        self._cancel_event = new_cancel_event()
        self._start_download()

    @work(thread=True, exclusive=True, group="download")
    def _start_download(self) -> None:
        import src.downloads as downloads

        app = self.app
        error_lines: list[str] = []

        def on_progress(line: str, pct: float) -> None:
            if self._cancelled:
                return
            if pct == downloads.PHASE_NEW_STREAM:
                self.app.call_from_thread(self._switch_to_audio_phase)
            elif pct == downloads.PHASE_POSTPROCESS:
                self.app.call_from_thread(self._switch_to_postprocess, line)
            elif pct >= 0:
                self.app.call_from_thread(self._update_progress, pct, line)
            stripped = line.strip()
            if stripped.startswith("ERROR:") or "error" in stripped.lower():
                error_lines.append(stripped[:120])

        try:
            if self._audio_only:
                success = downloads.download_audio_with_progress(
                    self._video_id,
                    app.config,
                    on_progress=on_progress,
                    cancel=self._cancel_event,
                )
            else:
                success = downloads.download_video_with_progress(
                    self._video_id,
                    app.config,
                    quality_format=self._fmt,
                    on_progress=on_progress,
                    cancel=self._cancel_event,
                )
        except RuntimeError as exc:
            success = False
            error_lines.append(str(exc))
        except Exception as exc:
            success = False
            error_lines.append(f"Unexpected error: {exc}")
        finally:
            from src.ytdlp import release_cancel_event

            release_cancel_event(self._cancel_event)

        if not self._cancelled:
            err = error_lines[-1] if error_lines else ""
            self.app.call_from_thread(self._on_done, success, err)

    def _switch_to_audio_phase(self) -> None:
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
            try:
                library.invalidate_cache()
            except Exception:
                pass
            self.dismiss(True)
        else:
            try:
                self.query_one("#download-title", Static).update(
                    "[bold red]\u26a0  Download failed[/bold red]"
                )
                msg = error_msg or "yt-dlp returned an error -- check network or browser auth."
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

    def action_audio_pause(self) -> None:
        self.app.audio.toggle_audio_pause()

    def action_audio_stop(self) -> None:
        self.app.audio.stop_audio()

    def action_cancel_download(self) -> None:
        self._cancelled = True
        if self._cancel_event:
            self._cancel_event.set()
        self.dismiss(False)
