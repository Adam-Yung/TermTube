"""Tests for download progress phase detection in ytdlp._run_download_with_progress."""

import subprocess
import sys
import textwrap
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from src.ytdlp import (
    _PROGRESS_RE,
    _DESTINATION_RE,
    _POSTPROCESS_RE,
    PHASE_NEW_STREAM,
    PHASE_POSTPROCESS,
    _run_download_with_progress,
)


class TestRegexPatterns:
    def test_progress_re_matches_percentage(self):
        assert _PROGRESS_RE.search("[download]  45.2%")
        assert _PROGRESS_RE.search("[download] 100.0%")
        assert _PROGRESS_RE.search("[download]   0.0%")

    def test_progress_re_no_match_on_destination(self):
        assert not _PROGRESS_RE.search("[download] Destination: video.mp4")

    def test_destination_re_matches(self):
        assert _DESTINATION_RE.search("[download] Destination: video [id].f302.webm")
        assert _DESTINATION_RE.search("[download] Destination: audio [id].f251.webm")

    def test_postprocess_re_matches_merger(self):
        assert _POSTPROCESS_RE.search("[Merger] Merging formats into \"video.mp4\"")

    def test_postprocess_re_matches_extract_audio(self):
        assert _POSTPROCESS_RE.search("[ExtractAudio] Destination: audio.mp3")

    def test_postprocess_re_matches_ffmpeg_extract(self):
        assert _POSTPROCESS_RE.search("[FFmpegExtractAudio] Destination: audio.mp3")

    def test_postprocess_re_no_match_on_download(self):
        assert not _POSTPROCESS_RE.search("[download]  45.2%")


class TestRunDownloadPhases:
    """Test that _run_download_with_progress emits correct phase signals."""

    SIMULATED_VIDEO_OUTPUT = textwrap.dedent("""\
        [download] Destination: video [abc123].f302.webm
        [download]   0.0% of 50.00MiB at 5.00MiB/s ETA 00:10
        [download]  50.0% of 50.00MiB at 5.00MiB/s ETA 00:05
        [download] 100.0% of 50.00MiB at 5.00MiB/s ETA 00:00
        [download] Destination: video [abc123].f251.webm
        [download]   0.0% of 5.00MiB at 5.00MiB/s ETA 00:01
        [download]  50.0% of 5.00MiB at 5.00MiB/s ETA 00:00
        [download] 100.0% of 5.00MiB at 5.00MiB/s ETA 00:00
        [Merger] Merging formats into "video [abc123].mp4"
        Deleting original file video [abc123].f302.webm
        Deleting original file video [abc123].f251.webm
    """)

    SIMULATED_AUDIO_OUTPUT = textwrap.dedent("""\
        [download] Destination: audio [abc123].webm
        [download]   0.0% of 5.00MiB at 5.00MiB/s ETA 00:01
        [download]  50.0% of 5.00MiB at 5.00MiB/s ETA 00:00
        [download] 100.0% of 5.00MiB at 5.00MiB/s ETA 00:00
        [ExtractAudio] Destination: audio [abc123].mp3
        Deleting original file audio [abc123].webm
    """)

    def _run_with_simulated_output(self, output: str):
        """Run _run_download_with_progress with simulated subprocess output."""
        calls = []

        def on_progress(line: str, pct: float) -> None:
            calls.append((line, pct))

        mock_proc = MagicMock()
        mock_proc.stdout = iter(output.splitlines(keepends=True))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            with patch("src.platform.get_popen_kwargs", return_value={}):
                result = _run_download_with_progress(["fake_cmd"], on_progress)

        return result, calls

    def test_video_download_emits_phases(self):
        result, calls = self._run_with_simulated_output(self.SIMULATED_VIDEO_OUTPUT)
        assert result is True

        # First stream: no PHASE_NEW_STREAM emitted (stream_count == 1)
        # Progress updates for first stream
        progress_calls = [(l, p) for l, p in calls if p >= 0]
        assert len(progress_calls) == 6  # 3 per stream

        # Second stream: PHASE_NEW_STREAM emitted
        new_stream_calls = [(l, p) for l, p in calls if p == PHASE_NEW_STREAM]
        assert len(new_stream_calls) == 1

        # Post-processing: PHASE_POSTPROCESS emitted
        postprocess_calls = [(l, p) for l, p in calls if p == PHASE_POSTPROCESS]
        assert len(postprocess_calls) == 1
        assert "Merger" in postprocess_calls[0][0]

    def test_audio_download_emits_postprocess(self):
        result, calls = self._run_with_simulated_output(self.SIMULATED_AUDIO_OUTPUT)
        assert result is True

        # No PHASE_NEW_STREAM (only one stream)
        new_stream_calls = [(l, p) for l, p in calls if p == PHASE_NEW_STREAM]
        assert len(new_stream_calls) == 0

        # Post-processing: PHASE_POSTPROCESS emitted
        postprocess_calls = [(l, p) for l, p in calls if p == PHASE_POSTPROCESS]
        assert len(postprocess_calls) == 1
        assert "ExtractAudio" in postprocess_calls[0][0]

    def test_progress_percentages_correct(self):
        result, calls = self._run_with_simulated_output(self.SIMULATED_VIDEO_OUTPUT)
        progress_calls = [(l, p) for l, p in calls if p >= 0]

        # Video stream: 0, 50, 100
        assert progress_calls[0][1] == 0.0
        assert progress_calls[1][1] == 50.0
        assert progress_calls[2][1] == 100.0
        # Audio stream: 0, 50, 100
        assert progress_calls[3][1] == 0.0
        assert progress_calls[4][1] == 50.0
        assert progress_calls[5][1] == 100.0

    def test_non_progress_lines_emitted_with_negative_pct(self):
        result, calls = self._run_with_simulated_output(self.SIMULATED_VIDEO_OUTPUT)
        # "Deleting original file" lines should come through with pct=-1.0
        deleting_calls = [(l, p) for l, p in calls if "Deleting" in l]
        assert len(deleting_calls) == 2
        assert all(p == -1.0 for _, p in deleting_calls)
