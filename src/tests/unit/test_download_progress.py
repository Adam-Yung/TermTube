"""Tests for download progress hooks in ytdlp (new YoutubeDL-based API).

Validates _make_progress_hook and _make_postprocessor_hook behaviour,
plus the download_video_with_progress / download_audio_with_progress
functions with mocked yt_dlp.YoutubeDL.
"""

from __future__ import annotations

import sys
import threading
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from src.ytdlp import (
    PHASE_NEW_STREAM,
    PHASE_POSTPROCESS,
    _make_progress_hook,
    _make_postprocessor_hook,
    download_video_with_progress,
    download_audio_with_progress,
)


class TestMakeProgressHook:
    """Test _make_progress_hook logic."""

    def _make_cancel(self) -> threading.Event:
        return threading.Event()

    def test_downloading_with_total_bytes(self):
        calls: list[tuple[str, float]] = []
        cancel = self._make_cancel()
        hook = _make_progress_hook(lambda line, pct: calls.append((line, pct)), cancel)

        hook({'status': 'downloading', 'downloaded_bytes': 50, 'total_bytes': 100, '_default_template': 'dl...'})
        assert len(calls) == 1
        assert calls[0][1] == pytest.approx(50.0)

    def test_downloading_with_total_bytes_estimate(self):
        calls: list[tuple[str, float]] = []
        cancel = self._make_cancel()
        hook = _make_progress_hook(lambda line, pct: calls.append((line, pct)), cancel)

        hook({'status': 'downloading', 'downloaded_bytes': 25, 'total_bytes_estimate': 200, '_default_template': ''})
        assert calls[0][1] == pytest.approx(12.5)

    def test_downloading_zero_total_gives_negative(self):
        calls: list[tuple[str, float]] = []
        cancel = self._make_cancel()
        hook = _make_progress_hook(lambda line, pct: calls.append((line, pct)), cancel)

        hook({'status': 'downloading', 'downloaded_bytes': 10, '_default_template': ''})
        assert calls[0][1] == -1.0

    def test_finished_emits_postprocess(self):
        calls: list[tuple[str, float]] = []
        cancel = self._make_cancel()
        hook = _make_progress_hook(lambda line, pct: calls.append((line, pct)), cancel)

        hook({'status': 'finished', 'filename': '/tmp/video.mp4'})
        assert len(calls) == 1
        assert calls[0][1] == PHASE_POSTPROCESS
        assert "Post-processing" in calls[0][0]

    def test_no_callback_does_not_crash(self):
        cancel = self._make_cancel()
        hook = _make_progress_hook(None, cancel)
        hook({'status': 'downloading', 'downloaded_bytes': 10, 'total_bytes': 100, '_default_template': ''})
        hook({'status': 'finished', 'filename': '/tmp/x.mp4'})

    def test_cancel_raises_download_error(self):
        import yt_dlp
        cancel = self._make_cancel()
        cancel.set()
        hook = _make_progress_hook(None, cancel)
        with pytest.raises(yt_dlp.utils.DownloadError, match="Cancelled"):
            hook({'status': 'downloading', 'downloaded_bytes': 0, 'total_bytes': 100, '_default_template': ''})

    def test_progress_percentages_correct(self):
        calls: list[tuple[str, float]] = []
        cancel = self._make_cancel()
        hook = _make_progress_hook(lambda line, pct: calls.append((line, pct)), cancel)

        hook({'status': 'downloading', 'downloaded_bytes': 0, 'total_bytes': 1000, '_default_template': ''})
        hook({'status': 'downloading', 'downloaded_bytes': 500, 'total_bytes': 1000, '_default_template': ''})
        hook({'status': 'downloading', 'downloaded_bytes': 1000, 'total_bytes': 1000, '_default_template': ''})

        assert calls[0][1] == pytest.approx(0.0)
        assert calls[1][1] == pytest.approx(50.0)
        assert calls[2][1] == pytest.approx(100.0)


class TestMakePostprocessorHook:
    """Test _make_postprocessor_hook logic."""

    def test_started_status_emits_postprocess(self):
        calls: list[tuple[str, float]] = []
        hook = _make_postprocessor_hook(lambda line, pct: calls.append((line, pct)))

        hook({'status': 'started', 'postprocessor': 'Merger'})
        assert len(calls) == 1
        assert calls[0][1] == PHASE_POSTPROCESS
        assert "Merger" in calls[0][0]

    def test_finished_status_ignored(self):
        calls: list[tuple[str, float]] = []
        hook = _make_postprocessor_hook(lambda line, pct: calls.append((line, pct)))

        hook({'status': 'finished', 'postprocessor': 'Merger'})
        assert len(calls) == 0

    def test_no_callback_does_not_crash(self):
        hook = _make_postprocessor_hook(None)
        hook({'status': 'started', 'postprocessor': 'FFmpegExtractAudio'})


class TestDownloadVideoWithProgress:
    """Test download_video_with_progress with mocked YoutubeDL."""

    def _fake_config(self, tmp_path):
        cfg = MagicMock()
        cfg.video_dir = tmp_path / "videos"
        cfg.audio_dir = tmp_path / "audio"
        cfg.video_format = "%(title)s.%(ext)s"
        cfg.audio_format = "%(title)s.%(ext)s"
        cfg.preferred_quality = "1080"
        cfg.cookies_file = None
        return cfg

    def test_returns_true_on_success(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 0
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", config)
        assert result is True

    def test_returns_false_on_failure(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 1
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", config)
        assert result is False

    def test_returns_false_on_download_error(self, tmp_path):
        import yt_dlp
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("fail")
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_video_with_progress("abc123def45", config)
        assert result is False

    def test_quality_format_override(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 0
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        captured_opts = {}
        def capture_ydl(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_video_with_progress("abc123def45", config, quality_format="bestvideo+bestaudio/best")

        assert captured_opts.get('format') == "bestvideo+bestaudio/best"
        assert captured_opts.get('merge_output_format') == 'mp4'


class TestDownloadAudioWithProgress:
    """Test download_audio_with_progress with mocked YoutubeDL."""

    def _fake_config(self, tmp_path):
        cfg = MagicMock()
        cfg.video_dir = tmp_path / "videos"
        cfg.audio_dir = tmp_path / "audio"
        cfg.audio_format = "%(title)s.%(ext)s"
        cfg.preferred_quality = "best"
        cfg.cookies_file = None
        return cfg

    def test_returns_true_on_success(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 0
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_audio_with_progress("xyz789ghj12", config)
        assert result is True

    def test_returns_false_on_failure(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 1
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        with patch("src.ytdlp.yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            result = download_audio_with_progress("xyz789ghj12", config)
        assert result is False

    def test_audio_opts_correct(self, tmp_path):
        config = self._fake_config(tmp_path)
        mock_ydl = MagicMock()
        mock_ydl.download.return_value = 0
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        captured_opts = {}
        def capture_ydl(opts):
            captured_opts.update(opts)
            return mock_ydl

        with patch("src.ytdlp.yt_dlp.YoutubeDL", side_effect=capture_ydl), \
             patch("src.ytdlp._base_opts", return_value={}):
            download_audio_with_progress("xyz789ghj12", config)

        assert captured_opts.get('format') == 'bestaudio/best'
        assert captured_opts.get('writeinfojson') is True
        assert captured_opts.get('writethumbnail') is True
        pp = captured_opts.get('postprocessors', [])
        assert any(p.get('key') == 'FFmpegExtractAudio' for p in pp)
        audio_pp = next(p for p in pp if p.get('key') == 'FFmpegExtractAudio')
        assert audio_pp['preferredcodec'] == 'mp3'
        assert audio_pp['preferredquality'] == '0'


class TestPhaseConstants:
    """Verify backward-compat constants still exist."""

    def test_phase_new_stream_value(self):
        assert PHASE_NEW_STREAM == -2.0

    def test_phase_postprocess_value(self):
        assert PHASE_POSTPROCESS == -3.0
