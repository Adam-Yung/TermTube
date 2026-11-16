#!/usr/bin/env python3
"""End-to-end run of the real app in a real pseudo-terminal, with no network.

Launches TermTube the way a user does, presses real keys, plays a generated tone from the Library through a real mpv,
and checks both the screen and mpv itself (over the app's IPC). Exit 0 only if every step passed. What a green run
means: the app starts, renders, scans the library, starts and controls mpv (poll, pause, seek, stop), records history
and quits cleanly on this platform.
It is silent: mpv gets an isolated config with ao=null.
Usage: scripts/e2e-local.py [--app-dir DIR] [--python EXE] [--launcher PATH] [--keep] [--debug-log]
  --app-dir   the checkout or the installed copy to run and import from (default: this checkout)
  --launcher  run this launcher (termtube / termtube.cmd) instead of ``python src/main.py``
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import shutil
import struct
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

ROWS, COLS = 40, 130
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-2AB]|\x1b[=>78]")
KEYS = {"F4": "\x1b[14~", "F5": "\x1b[15~", "space": " "}
TONE_ID, TONE_TITLE = "TONE0000001", "E2E Test Tone"
SEED_TITLE = "E2E Seed Video"
failures: list[str] = []


class PosixTerminal:
    """The app on a stdlib pty."""

    def __init__(self, argv: list[str], env: dict, cwd: str) -> None:
        import fcntl
        import pty
        import termios

        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # child: size the terminal, then become the app
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
            os.chdir(cwd)
            os.execvpe(argv[0], argv, env)
        self.status: int | None = None

    def read(self, timeout: float) -> str:
        import select

        if select.select([self.fd], [], [], timeout)[0]:
            try:
                return os.read(self.fd, 65536).decode("utf-8", "replace")
            except OSError:  # EIO once the child has exited
                return ""
        return ""

    def write(self, data: str) -> None:
        os.write(self.fd, data.encode())

    def exit_code(self, timeout: float) -> int | None:
        deadline = time.monotonic() + timeout
        while self.status is None and time.monotonic() < deadline:
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.status = os.waitstatus_to_exitcode(status)
            else:
                self.read(0.1)  # keep draining so the app never blocks on a full pty
        return self.status

    def kill(self) -> None:
        import signal

        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except OSError:
                pass


class WindowsTerminal:
    """The app on a ConPTY through pywinpty."""

    def __init__(self, argv: list[str], env: dict, cwd: str) -> None:
        from winpty import PtyProcess

        self.proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(ROWS, COLS))
        self.chunks: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        while True:
            try:
                self.chunks.put(self.proc.read(65536))
            except Exception:  # EOFError when the process ends
                return

    def read(self, timeout: float) -> str:
        try:
            return self.chunks.get(timeout=timeout)
        except queue.Empty:
            return ""

    def write(self, data: str) -> None:
        self.proc.write(data)

    def exit_code(self, timeout: float) -> int | None:
        deadline = time.monotonic() + timeout
        while self.proc.isalive() and time.monotonic() < deadline:
            self.read(0.1)
        return None if self.proc.isalive() else self.proc.wait()

    def kill(self) -> None:
        if self.proc.isalive():
            self.proc.terminate(force=True)


class Session:
    """A terminal plus everything it has printed, with expect-style waiting on text printed after a mark."""

    def __init__(self, terminal) -> None:
        self.term = terminal
        self.raw = ""

    def pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.raw += self.term.read(0.1)

    def mark(self) -> int:
        return len(self.raw)

    def text_since(self, mark: int) -> str:
        return ANSI.sub("", self.raw[mark:])

    def expect(self, needle: str, mark: int, timeout: float = 20.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump(0.3)
            if needle in self.text_since(mark):
                return True
        return False

    def send(self, key: str) -> None:
        self.term.write(KEYS.get(key, key))


def step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(': ' + detail) if detail else ''}", flush=True)
    if not ok:
        failures.append(name)
    return ok


def wait_for(condition, timeout: float, session: Session, interval: float = 0.3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        session.pump(interval)
    return None


def write_tone(path: Path) -> None:
    rate = 8000
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        samples = (int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate * 30))
        out.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def prepare(tmp: Path, app_dir: Path) -> dict:
    """Private config, cache, IPC directory, a Library entry and a seeded Home feed; returns the app's environment."""
    audio, video, cfg, run = tmp / "audio", tmp / "video", tmp / "cfg", tmp / "run"
    for directory in (audio, video, cfg):
        directory.mkdir()
    run.mkdir(mode=0o700)
    write_tone(audio / "tone-e2e.wav")
    sidecar = {"id": TONE_ID, "title": TONE_TITLE, "uploader": "TermTube CI", "duration": 30, "upload_date": "20260101"}
    (audio / "tone-e2e.info.json").write_text(json.dumps(sidecar), encoding="utf-8")

    import yaml

    (tmp / "config.yaml").write_text(yaml.safe_dump({
        "browser": "none", "video_dir": str(video), "audio_dir": str(audio), "thumbnail_warning_dismissed": True,
        "sponsorblock": {"enabled": False, "auto_skip": False},
    }), encoding="utf-8")
    # mpv reads this config (MPV_HOME works on every platform): silent, no audio device needed (CI runners have none)
    mpv_conf = cfg / "mpv"
    mpv_conf.mkdir()
    (mpv_conf / "mpv.conf").write_text("ao=null\n", encoding="utf-8")
    # COLUMNS and LINES override the pty's size (pytest sets 80x24 in its children): pin them to the size we made
    env = dict(os.environ, MPV_HOME=str(mpv_conf), TERM="xterm-256color", COLORTERM="truecolor",
               TERMTUBE_CACHE_DIR=str(tmp / "cache"), COLUMNS=str(COLS), LINES=str(ROWS))
    if os.name == "nt":
        env.update(APPDATA=str(cfg), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    else:
        env.update(XDG_CONFIG_HOME=str(cfg), XDG_RUNTIME_DIR=str(run))
    private = ("TERMTUBE_CACHE_DIR", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "APPDATA")
    os.environ.update({k: env[k] for k in private if k in env})
    sys.path.insert(0, str(app_dir))

    from src.cache import Cache

    cache = Cache({})
    entries = [
        {"id": f"E2E{i:08d}", "title": f"{SEED_TITLE} {i}", "uploader": "Seed", "duration": 100 + i,
         "view_count": 1000 * i, "upload_date": "20260101"}
        for i in range(1, 21)
    ]
    for entry in entries:
        cache.put_video(entry)
    cache.put_feed("home", [e["id"] for e in entries])
    cache.put_home_stash(entries)
    return env


def print_app_log(started_at: float) -> None:
    """The newest --debug log the app wrote since this run began (its own account of why something failed)."""
    logs = [p for p in (Path(tempfile.gettempdir()) / "TermTube").glob("*.log") if p.stat().st_mtime >= started_at - 5]
    if not logs:
        print("\n--- no app debug log found ---")
        return
    app_logs = [p for p in logs if not p.stem.endswith("-mpv")]
    for log in (max(app_logs, key=lambda p: p.stat().st_mtime), *sorted(p for p in logs if p.stem.endswith("-mpv"))):
        print(f"\n--- {log.name}, last 60 lines ---")
        print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))


def run(args, tmp: Path) -> int:
    app_dir = Path(args.app_dir).resolve()
    env = prepare(tmp, app_dir)
    from src import player

    socket_path = __import__("src.plat", fromlist=["x"]).get_audio_ipc_path()
    config = str(tmp / "config.yaml")
    extra = ["--debug"] if args.debug_log else []
    started_at = time.time()
    if args.launcher:
        argv = [args.launcher, "--config", config, *extra]
        if args.launcher.lower().endswith(".cmd"):
            argv = ["cmd.exe", "/c", *argv]
    else:
        argv = [args.python, str(app_dir / "src" / "main.py"), "--config", config, *extra]
    terminal = (WindowsTerminal if os.name == "nt" else PosixTerminal)(argv, env, str(app_dir))
    session = Session(terminal)

    def poll():
        return player.poll_audio_properties(socket_path=socket_path)

    try:
        if not step("starts and shows the Home feed from the cache", session.expect(f"{SEED_TITLE} 1", 0, 60)):
            return 1
        session.pump(1.0)

        mark = session.mark()
        session.send("F5")
        if not step("Library tab lists the local file", session.expect(TONE_TITLE, mark, 20)):
            return 1

        mark = session.mark()
        session.send("a")
        started = wait_for(lambda: (lambda r: r if r[0] is not None and r[1] else None)(poll()), 30, session)
        if not step("a: the app starts real mpv and it answers over IPC", started is not None):
            return 1
        step("a: the Now Playing bar is drawn", session.expect("Now Playing", mark, 10))
        pos0 = started[0]
        session.pump(1.5)
        pos1 = poll()[0]
        step("audio is advancing", pos1 is not None and pos1 > pos0 + 0.5, f"{pos0:.1f} -> {pos1}")

        mark = session.mark()
        session.send("space")
        paused = wait_for(lambda: poll()[2], 8, session)
        step("Space: mpv is paused", bool(paused))
        step("Space: the screen says PAUSED", session.expect("[PAUSED]", mark, 8))
        session.send("space")
        step("Space again: playing", wait_for(lambda: poll()[2] is False, 8, session) is not None)

        before = poll()[0] or 0.0
        session.send("]")
        # +5 s must show within 3 s; natural playback alone would add at most about 3 s, so only a real seek passes
        jumped = wait_for(lambda: (poll()[0] or 0) >= before + 4.5, 3, session, interval=0.15)
        step("]: seeks forward 5 s", bool(jumped), f"from {before:.1f}")

        mark = session.mark()
        session.send("x")
        gone = wait_for(lambda: poll()[0] is None, 10, session)
        step("x: mpv is stopped", gone is not None)
        step("x: the action bar returns", session.expect("Actions", mark, 10))

        mark = session.mark()
        session.send("F4")
        step("History tab shows the played track", session.expect(TONE_TITLE, mark, 15))

        session.send("q")
        code = terminal.exit_code(20)
        step("q: the app exits with code 0", code == 0, f"exit code {code}")
        step("no mpv left behind", poll()[0] is None)
    finally:
        still_running = terminal.exit_code(0) is None
        terminal.kill()
        if failures:
            print(f"\n(the app was {'still running' if still_running else 'no longer running'} at the end)")
            print("\n--- last screen output ---")
            print(ANSI.sub("", session.raw)[-1800:])
            if args.debug_log:
                print_app_log(started_at)
    print(f"\n{'OK: all steps passed' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--launcher")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--debug-log", action="store_true", help="run the app with --debug; print its log on failure")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the app's screen holds box-drawing and emoji
    tmp = Path(tempfile.mkdtemp(prefix="tt-", dir="/tmp" if os.name == "posix" else None))
    print(f"python {sys.version.split()[0]} on {sys.platform}; app: {args.launcher or args.app_dir}; workdir {tmp}")
    try:
        return run(args, tmp)
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
