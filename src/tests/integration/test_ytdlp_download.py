"""Integration tests for yt-dlp download functions with mocked YoutubeDL."""

from functools import partial
from unittest.mock import patch

import pytest

from src.downloads import (
    PHASE_POSTPROCESS,
    download_audio_with_progress,
    download_video_with_progress,
)
from src.tests.fakes import download_config, downloading_with, mock_ydl


def _record_percent(received, line, pct):
    received.append(pct)


def _fire_hooks(opts, key, events, urls):
    """A ``download`` that reports ``events`` to every hook registered under ``key``."""
    for hook in opts.get(key, []):
        for event in events:
            hook(event)
    return 0


@pytest.fixture
def fake_config(tmp_path):
    """Minimal config object with required attributes for download functions."""
    return download_config(tmp_path)


class TestDownloadVideoWithProgress:
    """Tests for download_video_with_progress."""

    def test_passes_correct_format_opts(self, fake_config):
        with downloading_with(mock_ydl()) as built:
            download_video_with_progress(
                "abc123def45", fake_config,
                quality_format="bestvideo+bestaudio/best",
            )

        captured_opts = built.opts
        assert captured_opts['format'] == "bestvideo+bestaudio/best"
        assert captured_opts['merge_output_format'] == "mp4"

    def test_preferred_quality_default_format(self, fake_config):
        fake_config.preferred_quality = "720"
        with downloading_with(mock_ydl()) as built:
            download_video_with_progress("abc123def45", fake_config)

        captured_opts = built.opts
        assert "720" in captured_opts['format']

    def test_progress_callback_receives_percentages(self, fake_config):
        received = []

        on_progress = partial(_record_percent, received)
        ydl = mock_ydl()
        with downloading_with(ydl) as built:
            events = [{'status': 'downloading', 'downloaded_bytes': done, 'total_bytes': 100, '_default_template': ''}
                      for done in (5, 50, 100)]
            ydl.download = partial(_fire_hooks, built.opts, 'progress_hooks', events)
            download_video_with_progress("abc123def45", fake_config, on_progress=on_progress)

        assert len(received) == 3
        assert received[0] == pytest.approx(5.0)
        assert received[1] == pytest.approx(50.0)
        assert received[2] == pytest.approx(100.0)

    def test_returns_true_on_success(self, fake_config):
        with downloading_with(mock_ydl()):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is True

    def test_returns_false_on_failure(self, fake_config):
        with downloading_with(mock_ydl(1)):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is False

    def test_returns_false_on_download_error(self, fake_config):
        import yt_dlp
        ydl = mock_ydl()
        ydl.download.side_effect = yt_dlp.utils.DownloadError("not found")

        with downloading_with(ydl):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is False

    def test_writeinfojson_and_writethumbnail(self, fake_config):
        with downloading_with(mock_ydl()) as built:
            download_video_with_progress("abc123def45", fake_config)

        captured_opts = built.opts
        assert captured_opts.get('writeinfojson') is True
        assert captured_opts.get('writethumbnail') is True


class TestDownloadAudioWithProgress:
    """Tests for download_audio_with_progress."""

    def test_passes_audio_extraction_opts(self, fake_config):
        with downloading_with(mock_ydl()) as built:
            download_audio_with_progress("xyz789ghj12", fake_config)

        captured_opts = built.opts
        assert captured_opts['format'] == "bestaudio/best"
        pp = captured_opts['postprocessors']
        assert any(p['key'] == 'FFmpegExtractAudio' for p in pp)
        audio_pp = next(p for p in pp if p['key'] == 'FFmpegExtractAudio')
        assert audio_pp['preferredcodec'] == 'mp3'
        assert audio_pp['preferredquality'] == '0'

    def test_format_is_bestaudio(self, fake_config):
        with downloading_with(mock_ydl()) as built:
            download_audio_with_progress("xyz789ghj12", fake_config)

        captured_opts = built.opts
        assert captured_opts['format'] == "bestaudio/best"

    def test_postprocessor_hook_emits_phase(self, fake_config):
        received = []

        on_progress = partial(_record_percent, received)
        ydl = mock_ydl()
        with downloading_with(ydl) as built:
            events = [{'status': 'started', 'postprocessor': 'FFmpegExtractAudio'}]
            ydl.download = partial(_fire_hooks, built.opts, 'postprocessor_hooks', events)
            download_audio_with_progress("xyz789ghj12", fake_config, on_progress=on_progress)

        assert PHASE_POSTPROCESS in received

    def test_writeinfojson_and_writethumbnail(self, fake_config):
        with downloading_with(mock_ydl()) as built:
            download_audio_with_progress("xyz789ghj12", fake_config)

        captured_opts = built.opts
        assert captured_opts.get('writeinfojson') is True
        assert captured_opts.get('writethumbnail') is True

    def test_returns_true_on_success(self, fake_config):
        with downloading_with(mock_ydl()):
            result = download_audio_with_progress("xyz789ghj12", fake_config)
        assert result is True

    def test_returns_false_on_failure(self, fake_config):
        with downloading_with(mock_ydl(1)):
            result = download_audio_with_progress("xyz789ghj12", fake_config)
        assert result is False


class TestUnsafeTemplates:
    def test_video_template_with_dotdot_never_starts_yt_dlp(self, fake_config):
        fake_config.video_format = "../%(title)s.%(ext)s"
        with patch("src.downloads.yt_dlp.YoutubeDL") as ydl, patch("src.downloads.base_opts", return_value={}):
            with pytest.raises(RuntimeError, match="Unsafe download template"):
                download_video_with_progress("abc123def45", fake_config)
        ydl.assert_not_called()

    def test_audio_template_that_is_absolute_never_starts_yt_dlp(self, fake_config):
        fake_config.audio_format = "/tmp/%(title)s.%(ext)s"
        with patch("src.downloads.yt_dlp.YoutubeDL") as ydl, patch("src.downloads.base_opts", return_value={}):
            with pytest.raises(RuntimeError, match="Unsafe download template"):
                download_audio_with_progress("abc123def45", fake_config)
        ydl.assert_not_called()
