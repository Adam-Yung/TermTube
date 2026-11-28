#!/usr/bin/env python3
"""Drive a real mpv through TermTube's own IPC code: the check that cannot be done with mocks.

Starts mpv silently (``--ao=null``) on a generated tone, so it needs no audio device, no file and no network, then uses
``src.player`` as the audio controller does: poll position and duration, pause, seek, quit. On Windows that is the named
pipe and pywin32; elsewhere the Unix socket. Usage: scripts/smoke-ipc.py [--require-mpv]
Exit 0: every step passed, or mpv is missing and --require-mpv was not given. Exit 1: a step failed.
Exit 2: mpv is missing and --require-mpv was given.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import player
from src.plat import _ipc_path, cleanup_ipc, get_popen_kwargs, terminate_process

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


def poll(socket_path: str) -> tuple:
    return player.poll_audio_properties(socket_path=socket_path)


def position(socket_path: str) -> float | None:
    return poll(socket_path)[0]


def full_answer(socket_path: str) -> tuple | None:
    """The poll result once mpv reports both a position and a duration."""
    pos, dur, paused = poll(socket_path)
    return (pos, dur, paused) if pos is not None and dur is not None else None


def tone_duration(socket_path: str) -> float | None:
    dur = poll(socket_path)[1]
    return dur if dur and abs(dur - 30) < 1.5 else None


def is_paused(socket_path: str) -> bool:
    return poll(socket_path)[2]


def is_playing(socket_path: str) -> bool:
    return poll(socket_path)[2] is False


def position_within(socket_path: str, low: float, high: float) -> bool:
    return in_range(position(socket_path), low, high)


def send(socket_path: str, *command) -> None:
    player.send_ipc_command({"command": list(command)}, socket_path=socket_path)


def check_playing(socket_path: str, pos0: float, dur: float) -> None:
    # a lavfi source reports a growing duration while mpv buffers it; wait for the real value
    settled = wait_for(partial(tone_duration, socket_path))
    step("duration reaches the tone's 30 s", settled is not None, f"{settled or dur:.1f} s")

    time.sleep(1.5)
    pos1 = position(socket_path)
    step("position advances while playing", pos1 is not None and pos1 > pos0 + 0.5, f"{pos0:.1f} -> {pos1}")


def check_pause(socket_path: str) -> None:
    send(socket_path, "cycle", "pause")
    paused = wait_for(partial(is_paused, socket_path))
    pos_a = position(socket_path)
    time.sleep(1.0)
    pos_b = position(socket_path)
    step("pause is reported and position holds", bool(paused) and pos_a is not None and abs(pos_b - pos_a) < 0.3,
         f"{pos_a} -> {pos_b}")
    send(socket_path, "cycle", "pause")
    step("resume", wait_for(partial(is_playing, socket_path)) is not None)


def check_seek(socket_path: str) -> None:
    send(socket_path, "seek", 20, "absolute")
    sought = wait_for(partial(position_within, socket_path, 19.5, 24))
    step("absolute seek to 20 s", bool(sought), f"now {position(socket_path)}")
    send(socket_path, "seek", -5, "relative")
    back = wait_for(partial(position_within, socket_path, 14, 20))
    step("relative seek of -5 s", bool(back), f"now {position(socket_path)}")


def check_quit(proc: subprocess.Popen, socket_path: str) -> None:
    send(socket_path, "quit")
    try:
        code = proc.wait(timeout=8)
        step("quit command ends mpv", code in (0, 4), f"exit code {code}")
    except subprocess.TimeoutExpired:
        step("quit command ends mpv", False, "still running after 8 s")


def drive(proc: subprocess.Popen, socket_path: str) -> bool:
    """Run every step; False when mpv never answered, so nothing else could be checked."""
    first = wait_for(partial(full_answer, socket_path))
    detail = f"{first}" if first else f"no answer in {STEP_TIMEOUT_S:.0f} s"
    if not step("connect and poll over IPC", first is not None, detail):
        return False
    pos0, dur, _ = first
    check_playing(socket_path, pos0, dur)
    check_pause(socket_path)
    check_seek(socket_path)
    check_quit(proc, socket_path)
    return True


def clean_up(proc: subprocess.Popen, socket_path: str, input_conf: str) -> None:
    terminate_process(proc, timeout=2.0)
    player.close_persistent_socket(socket_path)
    cleanup_ipc(socket_path)
    with contextlib.suppress(OSError):
        os.unlink(input_conf)
    err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace").strip()
    if proc.stderr:
        proc.stderr.close()
    if failures and err:
        print("  mpv stderr:", err[:600].replace("\n", " | "))


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
        if not drive(proc, socket_path):
            return 1
    finally:
        clean_up(proc, socket_path, input_conf)

    print(f"\n{'OK: all steps passed' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
