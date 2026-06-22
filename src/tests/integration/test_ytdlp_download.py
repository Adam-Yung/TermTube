"""Integration tests for yt-dlp download functions with mocked YoutubeDL."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.ytdlp import (
    download_video_with_progress,
    download_audio_with_progress,
    PHASE_POSTPROCESS,
    _make_progress_hook,
)


@pytest.fixture
def fake_config(tmp_path):
    """Minimal config object with required attributes for download functions."""
    cfg = MagicMock()
    cfg.video_dir = tmp_path / "videos"
    cfg.audio_dir = tmp_path / "audio"
    cfg.video_format = "%(title)s.%(ext)s"
    cfg.audio_format = "%(title)s.%(ext)s"
    cfg.preferred_quality = "1080"
    cfg.cookies_file = None
    return cfg


def _mock_ydl(return_code=0):
    """Create a mock YoutubeDL context manager."""
    mock = MagicMock()
    mock.download.return_value = return_code
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


class TestDownloadVideoWithProgress:
    """Tests for download_video_with_progress."""

    def test_passes_correct_format_opts(self, fake_config):
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_video_with_progress(
                "abc123def45", fake_config,
                quality_format="bestvideo+bestaudio/best",
            )

        assert captured_opts['format'] == "bestvideo+bestaudio/best"
        assert captured_opts['merge_output_format'] == "mp4"

    def test_preferred_quality_default_format(self, fake_config):
        fake_config.preferred_quality = "720"
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_video_with_progress("abc123def45", fake_config)

        assert "720" in captured_opts['format']

    def test_progress_callback_receives_percentages(self, fake_config):
        received = []

        def on_progress(line, pct):
            received.append(pct)

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_download(urls):
            opts = captured_opts
            hooks = opts.get('progress_hooks', [])
            for hook in hooks:
                hook({'status': 'downloading', 'downloaded_bytes': 5, 'total_bytes': 100, '_default_template': ''})
                hook({'status': 'downloading', 'downloaded_bytes': 50, 'total_bytes': 100, '_default_template': ''})
                hook({'status': 'downloading', 'downloaded_bytes': 100, 'total_bytes': 100, '_default_template': ''})
            return 0

        mock_ydl.download = fake_download
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_video_with_progress("abc123def45", fake_config, on_progress=on_progress)

        assert len(received) == 3
        assert received[0] == pytest.approx(5.0)
        assert received[1] == pytest.approx(50.0)
        assert received[2] == pytest.approx(100.0)

    def test_returns_true_on_success(self, fake_config):
        mock_ydl = _mock_ydl(0)
        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is True

    def test_returns_false_on_failure(self, fake_config):
        mock_ydl = _mock_ydl(1)
        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is False

    def test_returns_false_on_download_error(self, fake_config):
        import yt_dlp
        mock_ydl = MagicMock()
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("not found")
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is False

    def test_writeinfojson_and_writethumbnail(self, fake_config):
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_video_with_progress("abc123def45", fake_config)

        assert captured_opts.get('writeinfojson') is True
        assert captured_opts.get('writethumbnail') is True


class TestDownloadAudioWithProgress:
    """Tests for download_audio_with_progress."""

    def test_passes_audio_extraction_opts(self, fake_config):
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        assert captured_opts['format'] == "bestaudio/best"
        pp = captured_opts['postprocessors']
        assert any(p['key'] == 'FFmpegExtractAudio' for p in pp)
        audio_pp = next(p for p in pp if p['key'] == 'FFmpegExtractAudio')
        assert audio_pp['preferredcodec'] == 'mp3'
        assert audio_pp['preferredquality'] == '0'

    def test_format_is_bestaudio(self, fake_config):
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        assert captured_opts['format'] == "bestaudio/best"

    def test_postprocessor_hook_emits_phase(self, fake_config):
        received = []

        def on_progress(line, pct):
            received.append(pct)

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_download(urls):
            pp_hooks = captured_opts.get('postprocessor_hooks', [])
            for hook in pp_hooks:
                hook({'status': 'started', 'postprocessor': 'FFmpegExtractAudio'})
            return 0

        mock_ydl.download = fake_download
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config, on_progress=on_progress)

        assert PHASE_POSTPROCESS in received

    def test_writeinfojson_and_writethumbnail(self, fake_config):
        mock_ydl = _mock_ydl(0)
        captured_opts = {}

        def capture(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        assert captured_opts.get('writeinfojson') is True
        assert captured_opts.get('writethumbnail') is True

    def test_returns_true_on_success(self, fake_config):
        mock_ydl = _mock_ydl(0)
        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_audio_with_progress("xyz789ghj12", fake_config)
        assert result is True

    def test_returns_false_on_failure(self, fake_config):
        mock_ydl = _mock_ydl(1)
        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_audio_with_progress("xyz789ghj12", fake_config)
        assert result is False
