"""The playlist-run keys of input.conf against a real mpv: the exit code is what TermTube reads. Skipped without mpv."""

import os
import subprocess
import time

import pytest

from src import player
from src.plat import _ipc_path, cleanup_ipc, get_popen_kwargs, terminate_process

pytestmark = pytest.mark.skipif(player.mpv_exe(headless=True) is None, reason="mpv is not installed")

TONE = "av://lavfi:sine=frequency=440:duration=30"


@pytest.mark.parametrize("key,code", [(">", 10), ("<", 11), ("q", 12), ("CLOSE_WIN", 12), ("Meta+q", 12)])
def test_a_run_key_ends_mpv_with_its_code(key, code):
    socket_path = _ipc_path(f"termtube-seq-{os.getpid()}-{code}")
    input_conf = player.write_input_conf(sequence=True)
    exe = player.mpv_exe(headless=True)
    cmd = player.audio_command(exe, input_conf=input_conf, socket_path=socket_path, stream_url=TONE)
    cmd[1:1] = ["--no-config", "--ao=null"]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **get_popen_kwargs(headless=True)
    )
    try:
        deadline = time.monotonic() + 12
        while player.poll_audio_properties(socket_path=socket_path)[0] is None and time.monotonic() < deadline:
            time.sleep(0.2)
        player.send_ipc_command({"command": ["keypress", key]}, socket_path=socket_path)
        assert proc.wait(timeout=8) == code
    finally:
        terminate_process(proc, timeout=2.0)
        player.close_persistent_socket(socket_path)
        cleanup_ipc(socket_path)
        os.unlink(input_conf)


def test_end_of_file_is_exit_zero():
    input_conf = player.write_input_conf(sequence=True)
    cmd = [player.mpv_exe(headless=True), "--no-config", "--ao=null", f"--input-conf={input_conf}",
           "--no-input-terminal", "--", "av://lavfi:sine=duration=1"]
    try:
        assert subprocess.run(cmd, capture_output=True, timeout=20).returncode == 0
    finally:
        os.unlink(input_conf)
