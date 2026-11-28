"""The Windows named-pipe transport against fake pywin32 modules."""

import json
import sys
import types

import pytest

from src import mpv_ipc, player


class PipeError(Exception):
    pass


class FakePipe:
    """``chunks`` are the reads; ``log`` records writes and closes; ``missing`` refuses the open."""

    def __init__(self):
        self.chunks, self.log, self.missing = [], [], False

    def create_file(self, *args):
        if self.missing:
            raise PipeError()
        return "handle"

    def read_file(self, handle, size):
        if not self.chunks:
            raise PipeError()
        return 0, self.chunks.pop(0)

    def write_file(self, handle, data):
        self.log.append(data)

    def close_handle(self, handle):
        self.log.append("closed")

    def busy_wait(self, path, timeout_ms):
        raise PipeError()  # a busy wait must not stop the open


@pytest.fixture
def pipe(monkeypatch):
    state = FakePipe()
    win32file = types.SimpleNamespace(
        CreateFile=state.create_file, ReadFile=state.read_file, WriteFile=state.write_file,
        CloseHandle=state.close_handle, GENERIC_READ=1, GENERIC_WRITE=2, OPEN_EXISTING=3,
    )
    win32pipe = types.SimpleNamespace(
        WaitNamedPipe=state.busy_wait, SetNamedPipeHandleState=lambda *a: None, PIPE_READMODE_BYTE=0
    )
    modules = {"pywintypes": types.SimpleNamespace(error=PipeError), "win32file": win32file, "win32pipe": win32pipe}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(mpv_ipc, "IS_WINDOWS", True)
    return state


def reply(request_id, data):
    return (json.dumps({"request_id": request_id, "error": "success", "data": data}) + "\n").encode()


def test_a_command_returns_the_first_reply_line_and_closes(pipe):
    pipe.chunks = [b'{"error": ', b'"success"}\n']
    assert player.send_ipc_command({"command": ["quit"]}, socket_path="p") == {"error": "success"}
    assert pipe.log == [b'{"command": ["quit"]}\n', "closed"]


def test_a_missing_pipe_gives_nothing(pipe):
    pipe.missing = True
    assert player.send_ipc_command({"command": ["quit"]}, socket_path="p") is None
    assert player.poll_audio_properties(socket_path="p") == (None, None, False)
    assert pipe.log == []


def test_one_poll_reads_all_three_properties(pipe):
    pipe.chunks = [reply(0, 4) + reply(1, 8), reply(2, True)]
    assert player.poll_audio_properties(socket_path="p") == (4.0, 8.0, True)
    assert pipe.log[-1] == "closed"


def test_a_broken_read_keeps_what_arrived(pipe):
    pipe.chunks = [reply(0, 4)]
    assert player.poll_audio_properties(socket_path="p") == (4.0, None, False)


def test_without_pywin32_everything_is_empty(monkeypatch):
    monkeypatch.setattr(mpv_ipc, "IS_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "pywintypes", None)
    assert player.send_ipc_command({"command": ["quit"]}, socket_path="p") is None
    assert player.poll_audio_properties(socket_path="p") == (None, None, False)
