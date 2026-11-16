"""player.run_mpv_with_retries: one launch loop for audio and video."""

import subprocess
from unittest.mock import MagicMock

import pytest

from src import player


class FakePopen:
    """Popen stand-in; each instance takes the next scripted (returncode, stderr) or an exception to raise."""
    script: list = []
    launched: list = []

    def __init__(self, cmd, **kwargs):
        item = FakePopen.script.pop(0)
        if isinstance(item, Exception):
            raise item
        self.returncode, self._stderr = item
        FakePopen.launched.append((cmd, kwargs))

    def communicate(self):
        return None, self._stderr


@pytest.fixture(autouse=True)
def fake_mpv(monkeypatch):
    FakePopen.script, FakePopen.launched = [], []
    monkeypatch.setattr(player.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(player.time, "sleep", lambda s: None)
    registry = MagicMock()
    monkeypatch.setattr(player.ProcessRegistry, "get", staticmethod(lambda: registry))
    return registry


def run(**kwargs):
    kwargs.setdefault("is_stale", lambda: False)
    return player.run_mpv_with_retries(lambda attempt: ["mpv", str(attempt)], headless=True, **kwargs)


@pytest.mark.parametrize("code,status", [(0, "ok"), (4, "ok"), (3, "killed")])
def test_normal_exits_do_not_retry(code, status):
    FakePopen.script[:] = [(code, "")]
    assert run().status == status
    assert len(FakePopen.launched) == 1


def test_abnormal_exit_retries_with_a_new_command_then_succeeds():
    retries = []
    FakePopen.script[:] = [(2, "boom"), (0, "")]
    outcome = run(on_retry=retries.append)
    assert outcome.status == "ok" and retries == [1]
    assert [cmd for cmd, _ in FakePopen.launched] == [["mpv", "1"], ["mpv", "2"]]


def test_gives_up_after_max_attempts_and_keeps_stderr():
    FakePopen.script[:] = [(1, "first"), (1, "second"), (1, "No audio stream")]
    outcome = run(capture_stderr=True)
    assert (outcome.status, outcome.returncode, outcome.stderr) == ("failed", 1, "No audio stream")
    assert len(FakePopen.launched) == 3


def test_stale_before_launch_and_after_exit():
    assert run(is_stale=lambda: True).status == "stale" and not FakePopen.launched
    FakePopen.script[:] = [(0, "")]
    flags = iter([False, True])
    assert run(is_stale=lambda: next(flags)).status == "stale"


def test_launch_errors_are_not_retried():
    FakePopen.script[:] = [FileNotFoundError()]
    outcome = run()
    assert outcome.status == "launch_error" and "mpv not found" in outcome.message
    FakePopen.script[:] = [PermissionError("denied")]
    assert "denied" in run().message


def test_spawn_hook_registers_and_stderr_capture_follows_the_flag(fake_mpv):
    spawned = []
    FakePopen.script[:] = [(0, "")]
    run(on_spawn=lambda proc, attempt: spawned.append(attempt), capture_stderr=True)
    assert spawned == [1]
    fake_mpv.register.assert_called_once()
    fake_mpv.unregister.assert_called_once()
    kwargs = FakePopen.launched[0][1]
    assert kwargs["stderr"] == subprocess.PIPE and kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8" and kwargs["errors"] == "replace"
    FakePopen.script[:] = [(0, "")]
    run()
    assert FakePopen.launched[1][1]["stderr"] == subprocess.DEVNULL
