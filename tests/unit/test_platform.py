"""Tests for src/platform.py -- Platform abstraction layer."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.platform import (
    IS_WINDOWS,
    IS_MACOS,
    IS_LINUX,
    get_cache_dir,
    get_config_dir,
    get_data_dir,
    get_audio_ipc_path,
    get_video_ipc_path,
    get_ipc_path,
    install_hint,
    terminate_process,
    get_subprocess_flags,
    cleanup_ipc,
)


# ── OS Constants ──────────────────────────────────────────────────────────────


class TestOSConstants:
    def test_is_windows_exists(self):
        assert isinstance(IS_WINDOWS, bool)

    def test_is_macos_exists(self):
        assert isinstance(IS_MACOS, bool)

    def test_is_linux_exists(self):
        assert isinstance(IS_LINUX, bool)

    def test_exactly_one_platform_true(self):
        active = sum([IS_WINDOWS, IS_MACOS, IS_LINUX])
        assert active == 1


# ── get_cache_dir ─────────────────────────────────────────────────────────────


class TestGetCacheDir:
    def test_returns_path_instance(self):
        result = get_cache_dir()
        assert isinstance(result, Path)

    def test_respects_xdg_cache_home(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        monkeypatch.setenv("XDG_CACHE_HOME", "/custom/cache")

        result = get_cache_dir()
        assert result == Path("/custom/cache/termtube")

    def test_falls_back_to_dot_cache(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        result = get_cache_dir()
        assert ".cache" in str(result)
        assert result.name == "termtube"

    def test_windows_uses_localappdata(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\Test\\AppData\\Local")

        result = get_cache_dir()
        assert result == Path("C:\\Users\\Test\\AppData\\Local/TermTube/cache")


# ── IPC Paths ─────────────────────────────────────────────────────────────────


class TestIPCPaths:
    def test_audio_ipc_path_returns_string(self):
        result = get_audio_ipc_path()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_video_ipc_path_returns_string(self):
        result = get_video_ipc_path()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_audio_and_video_paths_differ(self):
        assert get_audio_ipc_path() != get_video_ipc_path()

    def test_unix_audio_path(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        result = get_audio_ipc_path()
        assert result.endswith(".sock")

    def test_unix_video_path(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        result = get_video_ipc_path()
        assert result.endswith(".sock")

    def test_windows_audio_path(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        result = get_audio_ipc_path()
        assert "pipe" in result

    def test_windows_video_path(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        result = get_video_ipc_path()
        assert "pipe" in result


# ── install_hint ──────────────────────────────────────────────────────────────


class TestInstallHint:
    def test_returns_string(self):
        result = install_hint("mpv")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_known_tool_macos(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        monkeypatch.setattr("src.platform.IS_MACOS", True)
        assert "brew" in install_hint("mpv")

    def test_known_tool_linux(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        monkeypatch.setattr("src.platform.IS_MACOS", False)
        assert "apt" in install_hint("mpv")

    def test_known_tool_windows(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        assert "winget" in install_hint("mpv")

    def test_unknown_tool_returns_fallback(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        monkeypatch.setattr("src.platform.IS_MACOS", True)
        result = install_hint("nonexistent_tool_xyz")
        assert "nonexistent_tool_xyz" in result

    def test_all_known_tools_have_hints(self):
        for tool in ("yt-dlp", "mpv", "chafa", "ffmpeg"):
            hint = install_hint(tool)
            assert isinstance(hint, str)
            assert len(hint) > 0


# ── terminate_process ─────────────────────────────────────────────────────────


class TestTerminateProcess:
    def test_handles_none_process(self):
        terminate_process(None)

    def test_handles_already_dead_process(self):
        proc = MagicMock()
        proc.poll.return_value = 0
        terminate_process(proc)
        proc.terminate.assert_not_called()

    def test_terminates_running_process(self):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.return_value = 0
        terminate_process(proc)
        proc.terminate.assert_called_once()

    def test_kills_process_on_terminate_timeout(self):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.terminate.return_value = None
        proc.wait.side_effect = [Exception("timed out"), None]

        terminate_process(proc, timeout=1.0)

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    def test_survives_kill_failure(self):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.terminate.side_effect = Exception("access denied")
        proc.kill.side_effect = Exception("access denied")
        proc.wait.side_effect = Exception("not running")

        terminate_process(proc)


# ── get_subprocess_flags ──────────────────────────────────────────────────────


class TestSubprocessFlags:
    def test_unix_returns_empty_dict(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        result = get_subprocess_flags()
        assert result == {}

    def test_windows_returns_creation_flags(self, monkeypatch):
        import subprocess
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        if not hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            result = get_subprocess_flags()
            assert "creationflags" in result
        finally:
            if sys.platform != "win32":
                delattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
                delattr(subprocess, "CREATE_NO_WINDOW")


# ── cleanup_ipc ───────────────────────────────────────────────────────────────


class TestCleanupIPC:
    def test_unix_removes_socket_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        sock_file = tmp_path / "test.sock"
        sock_file.write_text("")
        cleanup_ipc(str(sock_file))
        assert not sock_file.exists()

    def test_unix_ignores_missing_file(self, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", False)
        cleanup_ipc("/tmp/nonexistent_socket_file_xyz.sock")

    def test_windows_does_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.platform.IS_WINDOWS", True)
        sock_file = tmp_path / "test.sock"
        sock_file.write_text("")
        cleanup_ipc(str(sock_file))
        assert sock_file.exists()
