from __future__ import annotations

import threading
from collections.abc import Callable

import yt_dlp

from src import logger
from src.ytdlp import base_opts, new_cancel_event, release_cancel_event

QUALITY_CHOICES: list[tuple[str, str]] = [
    ("best  (highest available)",          "bestvideo+bestaudio/best"),
    ("1080p (Full HD)",                    "bestvideo[height<=1080]+bestaudio/best"),
    ("720p  (HD)",                         "bestvideo[height<=720]+bestaudio/best"),
    ("480p  (SD)",                         "bestvideo[height<=480]+bestaudio/best"),
    ("360p  (low)",                        "bestvideo[height<=360]+bestaudio/best"),
    ("Audio only (best quality)",          "bestaudio/best"),
]

AUDIO_QUALITY_CHOICES: list[tuple[str, str]] = [
    ("best audio",   "bestaudio/best"),
    ("medium audio", "bestaudio[abr<=128]/bestaudio/best"),
]

PHASE_NEW_STREAM = -2.0
PHASE_POSTPROCESS = -3.0


def _make_progress_hook(on_progress: Callable[[str, float], None] | None, cancel: threading.Event):
    """yt-dlp progress hook that forwards to ``on_progress`` and aborts once ``cancel`` is set."""
    def hook(d: dict) -> None:
        if cancel.is_set():
            raise yt_dlp.utils.DownloadError("Cancelled by user")
        if on_progress is None:
            return
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                pct = downloaded / total * 100.0
            else:
                pct = -1.0
            on_progress(d.get('_default_template', ''), pct)
        elif status == 'finished':
            on_progress("Post-processing...", PHASE_POSTPROCESS)
    return hook


def _make_postprocessor_hook(on_progress: Callable[[str, float], None] | None):
    """yt-dlp postprocessor hook reporting merge/extraction as the post-process phase."""
    def hook(d: dict) -> None:
        if on_progress is None:
            return
        status = d.get('status')
        if status == 'started':
            on_progress(f"[{d.get('postprocessor', 'PP')}] Processing...", PHASE_POSTPROCESS)
    return hook


def _quality_to_format(quality: str) -> str:
    """Convert a config quality value (e.g. 'best', '1080') to a format string."""
    if quality == "best":
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={quality}]+bestaudio/best"


def _run_download(
    video_id: str,
    opts: dict,
    on_progress: Callable[[str, float], None] | None,
    label: str,
    cancel: threading.Event | None,
) -> bool:
    """Download ``video_id`` with ``opts`` plus progress/cancel hooks. True on success.

    Setting ``cancel`` aborts at the next progress callback. Without one, a private event is used.
    """
    opts['writeinfojson'] = True
    opts['writethumbnail'] = True
    opts['noprogress'] = True
    owned = cancel is None
    cancel = cancel or new_cancel_event()
    opts['progress_hooks'] = [_make_progress_hook(on_progress, cancel)]
    opts['postprocessor_hooks'] = [_make_postprocessor_hook(on_progress)]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.download([f"https://www.youtube.com/watch?v={video_id}"]) == 0
    except yt_dlp.utils.DownloadError as exc:
        logger.debug("%s error: %s", label, exc)
        return False
    finally:
        if owned:
            release_cancel_event(cancel)


def download_video_with_progress(
    video_id: str,
    config,
    *,
    quality_format: str = "",
    on_progress: Callable[[str, float], None] | None = None,
    cancel: threading.Event | None = None,
) -> bool:
    """Download video; ``quality_format`` overrides ``config.preferred_quality``. Set ``cancel`` to abort."""
    config.video_dir.mkdir(parents=True, exist_ok=True)
    fmt = quality_format or _quality_to_format(config.preferred_quality)
    logger.info("download_video %s (format=%s)", video_id, fmt)

    opts = base_opts(skip_manifests=False)
    opts['format'] = fmt
    opts['merge_output_format'] = 'mp4'
    opts['outtmpl'] = str(config.video_dir / config.video_format)
    return _run_download(video_id, opts, on_progress, "download_video", cancel)


def download_audio_with_progress(
    video_id: str,
    config,
    *,
    on_progress: Callable[[str, float], None] | None = None,
    cancel: threading.Event | None = None,
) -> bool:
    """Download audio as mp3. Set ``cancel`` to abort."""
    config.audio_dir.mkdir(parents=True, exist_ok=True)
    logger.info("download_audio %s", video_id)

    opts = base_opts(skip_manifests=False)
    opts['format'] = 'bestaudio/best'
    opts['outtmpl'] = str(config.audio_dir / config.audio_format)
    opts['postprocessors'] = [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '0',
    }]
    return _run_download(video_id, opts, on_progress, "download_audio", cancel)
