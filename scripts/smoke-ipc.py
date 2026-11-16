#!/usr/bin/env python3
"""Drive a real mpv through TermTube's own IPC code: the check that cannot be done with mocks.

Starts mpv silently (``--ao=null``) on a generated tone, so it needs no audio device, no file and no network, then uses
``src.player`` as the audio controller does: poll position and duration, pause, seek, quit. On Windows that is the named
pipe and pywin32; elsewhere the Unix socket. Usage: scripts/smoke-ipc.py [--require-mpv]
Exit 0: every step passed, or mpv is missing and --require-mpv was not given. Exit 1: a step failed.
Exit 2: mpv is missing and --require-mpv was given.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import player  # noqa: E402
from src.plat import _ipc_path, cleanup_ipc, get_popen_kwargs, terminate_process  # noqa: E402

TONE = "av://lavfi:sine=frequency=440:duration=30"
STEP_TIMEOUT_S = 12.0
failures: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(': ' + detail) if detail else ''}", flush=True)
    if not ok:
        failures.append(name)
    return ok


def wait_for(condition, timeout: float = STEP_TIMEOUT_S, interval: float = 0.2):
    """Poll ``condition()`` until it returns something truthy; that value, or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    return None


def in_range(value: float | None, low: float, high: float) -> bool:
    return value is not None and low <= value < high


def main() -> int:
    require = "--require-mpv" in sys.argv
    exe = player.mpv_exe(headless=True)
    print(f"python {sys.version.split()[0]} on {sys.platform}; mpv: {exe or 'not found'}")
    if not exe:
        print("SKIP: mpv not found" + (" (required)" if require else ""))
        return 2 if require else 0

    socket_path = _ipc_path(f"termtube-smoke-{os.getpid()}")
    input_conf = player.write_input_conf()
    cmd = player.audio_command(exe, input_conf=input_conf, socket_path=socket_path, title="smoke", stream_url=TONE)
    cmd[1:1] = ["--no-config", "--ao=null"]  # ignore the user's mpv.conf; no audio device needed
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **get_popen_kwargs(headless=True))
    try:
        def position():
            return player.poll_audio_properties(socket_path=socket_path)[0]

        def first_poll():
            pos, dur, paused = player.poll_audio_properties(socket_path=socket_path)
            return (pos, dur, paused) if pos is not None and dur is not None else None

        first = wait_for(first_poll)
        detail = f"{first}" if first else f"no answer in {STEP_TIMEOUT_S:.0f} s"
        if not step("connect and poll over IPC", first is not None, detail):
            return 1
        pos0, dur, _ = first
        step("duration is the tone's 30 s", abs(dur - 30) < 1.5, f"{dur:.1f} s")

        time.sleep(1.5)
        pos1, _, _ = player.poll_audio_properties(socket_path=socket_path)
        step("position advances while playing", pos1 is not None and pos1 > pos0 + 0.5, f"{pos0:.1f} -> {pos1}")

        player.send_ipc_command({"command": ["cycle", "pause"]}, socket_path=socket_path)
        paused = wait_for(lambda: player.poll_audio_properties(socket_path=socket_path)[2])
        pos_a, _, _ = player.poll_audio_properties(socket_path=socket_path)
        time.sleep(1.0)
        pos_b, _, _ = player.poll_audio_properties(socket_path=socket_path)
        step("pause is reported and position holds", bool(paused) and pos_a is not None and abs(pos_b - pos_a) < 0.3,
             f"{pos_a} -> {pos_b}")
        player.send_ipc_command({"command": ["cycle", "pause"]}, socket_path=socket_path)
        step("resume", wait_for(lambda: player.poll_audio_properties(socket_path=socket_path)[2] is False) is not None)

        player.send_ipc_command({"command": ["seek", 20, "absolute"]}, socket_path=socket_path)
        sought = wait_for(lambda: in_range(position(), 19.5, 24))
        step("absolute seek to 20 s", bool(sought), f"now {position()}")
        player.send_ipc_command({"command": ["seek", -5, "relative"]}, socket_path=socket_path)
        back = wait_for(lambda: in_range(position(), 14, 20))
        step("relative seek of -5 s", bool(back), f"now {position()}")

        player.send_ipc_command({"command": ["quit"]}, socket_path=socket_path)
        try:
            code = proc.wait(timeout=8)
            step("quit command ends mpv", code in (0, 4), f"exit code {code}")
        except subprocess.TimeoutExpired:
            step("quit command ends mpv", False, "still running after 8 s")
    finally:
        terminate_process(proc, timeout=2.0)
        player.close_persistent_socket(socket_path)
        cleanup_ipc(socket_path)
        try:
            os.unlink(input_conf)
        except OSError:
            pass
        err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace").strip()
        proc.stderr and proc.stderr.close()
        if failures and err:
            print("  mpv stderr:", err[:600].replace("\n", " | "))

    print(f"\n{'OK: all steps passed' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
