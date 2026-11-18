from __future__ import annotations

import threading
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static

from src import library, logger
from src.entries import Entry
from src.strings import text
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
        self._files: list[str] = []  # every file yt-dlp finished; the last is the media file
        self._cancel_event: threading.Event | None = None

    def compose(self) -> ComposeResult:
        title = self._entry.get("title", self._video_id)
        title_key = "title_audio" if self._audio_only else "title_video"
        with Vertical(id="download-dialog", classes="dialog"):
            yield Static(
                text(f"download_modal.{title_key}"),
                id="download-title",
                markup=True,
            )
            yield Static(
                text("download_modal.status_title", title=escape_markup(title[:60])),
                id="download-status",
                markup=True,
            )
            yield ProgressBar(total=100, show_eta=False, id="download-bar")
            audio = text("download_modal.hint_audio") if self.app.audio.is_playing else ""
            yield Static(
                text("download_modal.hint", audio=audio),
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
                    on_file=self._files.append,
                )
            else:
                success = downloads.download_video_with_progress(
                    self._video_id,
                    app.config,
                    quality_format=self._fmt,
                    on_progress=on_progress,
                    cancel=self._cancel_event,
                    on_file=self._files.append,
                )
        except RuntimeError as exc:
            success = False
            error_lines.append(str(exc))
        except Exception as exc:
            success = False
            error_lines.append(text("download_modal.unexpected_error", error=exc))
        finally:
            from src.ytdlp import release_cancel_event

            release_cancel_event(self._cancel_event)

        if not self._cancelled:
            err = error_lines[-1] if error_lines else ""
            self.app.call_from_thread(self._on_done, success, err)

    def _switch_to_audio_phase(self) -> None:
        try:
            self.query_one("#download-title", Static).update(
                text("download_modal.title_audio")
            )
            bar = self.query_one("#download-bar", ProgressBar)
            bar.progress = 0
            self.query_one("#download-status", Static).update(
                text("download_modal.status_audio_track")
            )
        except Exception:
            pass

    def _switch_to_postprocess(self, line: str) -> None:
        try:
            if "Merger" in line or "Merging" in line:
                label = text("download_modal.merging")
            elif "ExtractAudio" in line or "FFmpegExtractAudio" in line:
                label = text("download_modal.converting")
            else:
                label = text("download_modal.processing")
            self.query_one("#download-title", Static).update(
                text("download_modal.title_postprocess", label=label)
            )
            bar = self.query_one("#download-bar", ProgressBar)
            bar.update(total=None, progress=0)
            self.query_one("#download-status", Static).update(
                text("download_modal.status_wait")
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

    def _pin(self, entry: Entry | None) -> None:
        """Pin a downloaded video's metadata and thumbnail where cache pruning never reaches (Library works offline)."""
        if entry is None or not entry.get("id"):
            return
        cache = self.app.cache
        cache.pin_video(entry["id"], {k: v for k, v in entry.items() if not k.startswith("_")})
        thumb = entry.get("_thumb_path")
        cache.pin_thumb(entry["id"], Path(thumb) if thumb else None)

    def _registration_failed(self, exc: Exception) -> None:
        """The file is on disk; the Library scan indexes it later. Say so instead of hiding it."""
        logger.warning("download not registered in the Library: %s", type(exc).__name__)
        library.invalidate_cache()
        name = Path(self._files[-1]).name if self._files else text("download_modal.the_file")
        self.app.notify(
            text("download_modal.not_registered", name=name),
            severity="warning",
        )

    def _on_done(self, success: bool, error_msg: str = "") -> None:
        if success:
            try:
                bar = self.query_one("#download-bar", ProgressBar)
                bar.update(total=100, progress=100)
            except Exception:
                pass
            try:
                self._pin(library.finish_download(self._files))
            except Exception as exc:
                self._registration_failed(exc)
            self.dismiss(True)
        else:
            try:
                self.query_one("#download-title", Static).update(
                    text("download_modal.title_failed")
                )
                msg = error_msg or text("download_modal.default_error")
                self.query_one("#download-status", Static).update(
                    text("download_modal.status_error", message=escape_markup(msg[:80]))
                )
                self.query_one("#download-hint", Static).update(
                    text("download_modal.hint_close")
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
