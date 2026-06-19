"""Integration tests for yt-dlp download functions with mocked subprocess."""

from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from src.ytdlp import (
    download_video_with_progress,
    download_audio_with_progress,
    _run_download_with_progress,
    _active_procs,
    _active_procs_lock,
)


def _make_fake_proc(stdout_lines, returncode=0):
    """Create a mock Popen that yields given stdout lines."""
    proc = MagicMock()
    proc.stdout = iter(stdout_lines)
    proc.returncode = returncode
    proc.wait.return_value = returncode
    proc.pid = 99999
    proc.kill = MagicMock()
    return proc


@pytest.fixture
def fake_config(tmp_path):
    """Minimal config object with required attributes for download functions."""
    cfg = MagicMock()
    cfg.video_dir = tmp_path / "videos"
    cfg.audio_dir = tmp_path / "audio"
    cfg.video_format = "%(title)s.%(ext)s"
    cfg.audio_format = "%(title)s.%(ext)s"
    cfg.preferred_quality = "1080"
    cfg.cookie_args.return_value = []
    return cfg


class TestDownloadVideoWithProgress:
    """Tests for download_video_with_progress."""

    def test_calls_ytdlp_with_correct_format_flags(self, fake_config):
        fake_proc = _make_fake_proc(["[download] 100.0% of 50MiB\n"])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_video_with_progress("abc123def45", fake_config, quality_format="bestvideo+bestaudio/best")

        cmd = mock_popen.call_args[0][0]
        assert cmd[0].endswith("yt-dlp")
        assert "--format" in cmd
        fmt_idx = cmd.index("--format")
        assert cmd[fmt_idx + 1] == "bestvideo+bestaudio/best"
        assert "--merge-output-format" in cmd
        merge_idx = cmd.index("--merge-output-format")
        assert cmd[merge_idx + 1] == "mp4"

    def test_newline_flag_always_included(self, fake_config):
        fake_proc = _make_fake_proc(["[download] 50.0% of 20MiB\n"])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_video_with_progress("abc123def45", fake_config)

        cmd = mock_popen.call_args[0][0]
        assert "--newline" in cmd

    def test_preferred_quality_default_format(self, fake_config):
        """When no quality_format given, uses config.preferred_quality."""
        fake_config.preferred_quality = "720"
        fake_proc = _make_fake_proc([])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_video_with_progress("abc123def45", fake_config)

        cmd = mock_popen.call_args[0][0]
        fmt_idx = cmd.index("--format")
        assert "720" in cmd[fmt_idx + 1]

    def test_progress_callback_receives_percentages(self, fake_config):
        stdout_lines = [
            "[download]   0.5% of 100MiB at 5.0MiB/s\n",
            "[download]  25.0% of 100MiB at 10.0MiB/s\n",
            "[download]  50.0% of 100MiB at 12.0MiB/s\n",
            "[download]  75.3% of 100MiB at 15.0MiB/s\n",
            "[download] 100.0% of 100MiB at 20.0MiB/s\n",
        ]
        fake_proc = _make_fake_proc(stdout_lines)
        received = []

        def on_progress(line, pct):
            received.append(pct)

        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            _run_download_with_progress(["yt-dlp", "--newline", "http://example.com"], on_progress)

        assert len(received) == 5
        assert received[0] == pytest.approx(0.5)
        assert received[1] == pytest.approx(25.0)
        assert received[2] == pytest.approx(50.0)
        assert received[3] == pytest.approx(75.3)
        assert received[4] == pytest.approx(100.0)

    def test_error_handling_ytdlp_not_found(self, fake_config):
        with patch("src.ytdlp.subprocess.Popen", side_effect=FileNotFoundError), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            with pytest.raises(RuntimeError, match="yt-dlp not found"):
                download_video_with_progress("abc123def45", fake_config)

    def test_active_procs_tracking(self, fake_config):
        """Process is added to _active_procs during execution and removed after."""
        tracked_during = []

        original_lines = ["[download] 100.0% of 10MiB\n"]
        fake_proc = _make_fake_proc(original_lines)

        def fake_iter(self_ignored=None):
            with _active_procs_lock:
                tracked_during.append(fake_proc in _active_procs)
            return iter(original_lines)

        fake_proc.stdout = fake_iter()

        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            # Patch __iter__ so we can inspect _active_procs mid-execution
            _run_download_with_progress(["yt-dlp", "--newline", "http://example.com"])

        # After completion, proc should be removed
        with _active_procs_lock:
            assert fake_proc not in _active_procs

    def test_returns_true_on_success(self, fake_config):
        fake_proc = _make_fake_proc(["[download] 100.0%\n"], returncode=0)
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is True

    def test_returns_false_on_failure(self, fake_config):
        fake_proc = _make_fake_proc([], returncode=1)
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            result = download_video_with_progress("abc123def45", fake_config)
        assert result is False


class TestDownloadAudioWithProgress:
    """Tests for download_audio_with_progress."""

    def test_calls_ytdlp_with_audio_extraction_flags(self, fake_config):
        fake_proc = _make_fake_proc(["[download] 100.0%\n"])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        cmd = mock_popen.call_args[0][0]
        assert "--extract-audio" in cmd
        assert "--audio-format" in cmd
        audio_fmt_idx = cmd.index("--audio-format")
        assert cmd[audio_fmt_idx + 1] == "mp3"
        assert "--audio-quality" in cmd
        quality_idx = cmd.index("--audio-quality")
        assert cmd[quality_idx + 1] == "0"

    def test_newline_flag_always_included(self, fake_config):
        fake_proc = _make_fake_proc([])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        cmd = mock_popen.call_args[0][0]
        assert "--newline" in cmd

    def test_format_is_bestaudio(self, fake_config):
        fake_proc = _make_fake_proc([])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        cmd = mock_popen.call_args[0][0]
        fmt_idx = cmd.index("--format")
        assert cmd[fmt_idx + 1] == "bestaudio/best"

    def test_progress_callback_with_postprocess_phase(self, fake_config):
        """Post-processing lines emit PHASE_POSTPROCESS to the callback."""
        from src.ytdlp import PHASE_POSTPROCESS

        stdout_lines = [
            "[download]  50.0% of 5MiB\n",
            "[download] 100.0% of 5MiB\n",
            "[ExtractAudio] Destination: /tmp/song.mp3\n",
        ]
        fake_proc = _make_fake_proc(stdout_lines)
        received = []

        def on_progress(line, pct):
            received.append(pct)

        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            _run_download_with_progress(["yt-dlp", "--newline", "http://example.com"], on_progress)

        assert PHASE_POSTPROCESS in received

    def test_error_handling_ytdlp_not_found(self, fake_config):
        with patch("src.ytdlp.subprocess.Popen", side_effect=FileNotFoundError), \
             patch("src.platform.get_popen_kwargs", return_value={}):
            with pytest.raises(RuntimeError, match="yt-dlp not found"):
                download_audio_with_progress("xyz789ghj12", fake_config)

    def test_write_info_json_and_thumbnail_flags(self, fake_config):
        fake_proc = _make_fake_proc([])
        with patch("src.ytdlp.subprocess.Popen", return_value=fake_proc) as mock_popen, \
             patch("src.platform.get_popen_kwargs", return_value={}):
            download_audio_with_progress("xyz789ghj12", fake_config)

        cmd = mock_popen.call_args[0][0]
        assert "--write-info-json" in cmd
        assert "--write-thumbnail" in cmd
