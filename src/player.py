"""TermTube v2 — mpv IPC controller.

PlayerSession
-------------
Owns a single mpv process and a Unix socket IPC reader thread.
Uses observe_property to receive push events — zero polling.

Both audio and video playback go through the same PlayerSession:
  - Audio: mpv runs headlessly (--no-video --no-terminal).
  - Video: mpv opens a GUI window; the TUI stays live.

The socket reader thread is a daemon thread that feeds a queue.
Textual workers consume the queue and call call_from_thread to update UI.

Thread safety
-------------
All public methods are thread-safe and may be called from any thread.
Internal socket operations are serialised by _cmd_lock.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import logger

AUDIO_SOCK = Path("/tmp/termtube-mpv-audio.sock")
VIDEO_SOCK = Path("/tmp/termtube-mpv-video.sock")


class PlayMode(Enum):
    AUDIO = auto()
    VIDEO = auto()


@dataclass
class PlayerState:
    mode: PlayMode | None = None
    position: float = 0.0       # seconds
    duration: float = 0.0       # seconds
    paused: bool = False
    volume: int = 100
    idle: bool = True
    title: str = ""


@dataclass
class PropertyEvent:
    name: str
    value: Any


class PlayerSession:
    """Single mpv session that handles both audio and video."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._sock_path: Path = AUDIO_SOCK
        self._cmd_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._reader_stop = threading.Event()
        self._event_queue: queue.Queue[PropertyEvent] = queue.Queue()
        self._state = PlayerState()
        self._state_lock = threading.Lock()
        self._observe_id = 1

        # SponsorBlock auto-skip
        self._sb_segments: list[dict] = []   # [{start, end, category}, ...]
        self._sb_lock = threading.Lock()
        self._sb_skipped: set[int] = set()   # indices of already-skipped segments
        self._sb_enabled = False

        # Callbacks (set by UI layer)
        self._on_property_cbs: list[Callable[[PropertyEvent], None]] = []
        self._on_end_cbs: list[Callable[[int], None]] = []  # returncode
        self._on_error_cbs: list[Callable[[str], None]] = []
        self._on_skip_cbs: list[Callable[[dict], None]] = []  # segment dict

    # ------------------------------------------------------------------
    # Public callback registration
    # ------------------------------------------------------------------

    def on_property(self, cb: Callable[[PropertyEvent], None]) -> None:
        self._on_property_cbs.append(cb)

    def on_end(self, cb: Callable[[int], None]) -> None:
        self._on_end_cbs.append(cb)

    def on_error(self, cb: Callable[[str], None]) -> None:
        self._on_error_cbs.append(cb)

    def on_skip(self, cb: Callable[[dict], None]) -> None:
        """Register callback fired when a SponsorBlock segment is auto-skipped."""
        self._on_skip_cbs.append(cb)

    def clear_callbacks(self) -> None:
        self._on_property_cbs.clear()
        self._on_end_cbs.clear()
        self._on_error_cbs.clear()
        self._on_skip_cbs.clear()

    # ------------------------------------------------------------------
    # SponsorBlock
    # ------------------------------------------------------------------

    def set_segments(self, segments: list[dict], *, enabled: bool = True) -> None:
        """Load SponsorBlock segments for the current track.

        Must be called before or shortly after playback starts.
        Segments are dicts with keys: start (float), end (float), category (str).
        """
        with self._sb_lock:
            self._sb_segments = list(segments)
            self._sb_skipped = set()
            self._sb_enabled = enabled
        logger.debug("SponsorBlock: loaded %d segments (enabled=%s)", len(segments), enabled)

    def clear_segments(self) -> None:
        with self._sb_lock:
            self._sb_segments = []
            self._sb_skipped = set()
            self._sb_enabled = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> PlayerState:
        with self._state_lock:
            return PlayerState(
                mode=self._state.mode,
                position=self._state.position,
                duration=self._state.duration,
                paused=self._state.paused,
                volume=self._state.volume,
                idle=self._state.idle,
                title=self._state.title,
            )

    @property
    def is_playing(self) -> bool:
        with self._state_lock:
            return not self._state.idle and self._proc is not None

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play_audio(
        self,
        url: str,
        *,
        title: str = "",
        cookie_args: list[str] | None = None,
        ytdl_format: str = "bestaudio/best",
    ) -> None:
        """Start headless audio playback.  Blocks until mpv exits."""
        self._launch(
            url,
            mode=PlayMode.AUDIO,
            title=title,
            cookie_args=cookie_args or [],
            ytdl_format=ytdl_format,
            extra_args=["--no-video", "--no-terminal", "--msg-level=all=error"],
            sock_path=AUDIO_SOCK,
        )

    def play_video(
        self,
        url: str,
        *,
        title: str = "",
        cookie_args: list[str] | None = None,
        ytdl_format: str = "bestvideo+bestaudio/best",
    ) -> None:
        """Start video playback in a separate mpv window.  Blocks until mpv exits."""
        self._launch(
            url,
            mode=PlayMode.VIDEO,
            title=title,
            cookie_args=cookie_args or [],
            ytdl_format=ytdl_format,
            extra_args=["--really-quiet"],
            sock_path=VIDEO_SOCK,
        )

    def _launch(
        self,
        url: str,
        *,
        mode: PlayMode,
        title: str,
        cookie_args: list[str],
        ytdl_format: str,
        extra_args: list[str],
        sock_path: Path,
    ) -> None:
        self.stop()

        sock_path.unlink(missing_ok=True)
        self._sock_path = sock_path

        # Reset SponsorBlock skip tracking for the new track
        with self._sb_lock:
            self._sb_skipped = set()

        # Build ytdl-raw-options from cookie_args
        ytdl_raw: list[str] = []
        i = 0
        while i < len(cookie_args):
            if cookie_args[i] == "--cookies" and i + 1 < len(cookie_args):
                ytdl_raw.append(f"--ytdl-raw-options=cookies={cookie_args[i+1]}")
                i += 2
            elif cookie_args[i] == "--cookies-from-browser" and i + 1 < len(cookie_args):
                ytdl_raw.append(f"--ytdl-raw-options=cookies-from-browser={cookie_args[i+1]}")
                i += 2
            else:
                i += 1

        cmd = [
            "mpv",
            f"--input-ipc-server={sock_path}",
            f"--ytdl-format={ytdl_format}",
            *ytdl_raw,
            *extra_args,
            url,
        ]

        logger.debug("mpv launch: %s", " ".join(cmd))

        with self._state_lock:
            self._state.mode = mode
            self._state.idle = False
            self._state.title = title
            self._state.position = 0.0
            self._state.duration = 0.0
            self._state.paused = False

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Wait for socket to appear (up to 5s)
        for _ in range(50):
            if sock_path.exists():
                break
            time.sleep(0.1)

        # Start the observe_property reader thread
        self._reader_stop.clear()
        self._reader_thread = threading.Thread(
            target=self._socket_reader,
            daemon=True,
            name="mpv-ipc-reader",
        )
        self._reader_thread.start()

        # Block until mpv exits
        _, stderr_bytes = self._proc.communicate()
        returncode = self._proc.returncode

        # Teardown
        self._reader_stop.set()
        with self._state_lock:
            self._state.idle = True
            self._state.mode = None

        stderr_text = (stderr_bytes or b"").decode(errors="replace").strip()
        if returncode == 0 or returncode == 4:
            for cb in list(self._on_end_cbs):
                try:
                    cb(returncode)
                except Exception:
                    pass
        elif returncode == 3:
            # User quit mpv deliberately — silent
            for cb in list(self._on_end_cbs):
                try:
                    cb(returncode)
                except Exception:
                    pass
        else:
            first_line = stderr_text.splitlines()[0] if stderr_text else "unknown error"
            logger.warning("mpv exited %d: %s", returncode, first_line)
            for cb in list(self._on_error_cbs):
                try:
                    cb(first_line)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # IPC socket reader (observe_property push events)
    # ------------------------------------------------------------------

    def _socket_reader(self) -> None:
        """Daemon thread: open IPC socket, register observers, read events."""
        # Give mpv a moment to bind the socket
        for _ in range(30):
            if self._sock_path.exists():
                break
            time.sleep(0.1)
            if self._reader_stop.is_set():
                return

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(self._sock_path))
            sock.settimeout(0.5)
        except Exception as exc:
            logger.debug("IPC connect failed: %s", exc)
            return

        # Register observers
        for prop in ("time-pos", "duration", "pause", "volume", "media-title"):
            msg = json.dumps({"command": ["observe_property", self._observe_id, prop]}) + "\n"
            self._observe_id += 1
            try:
                sock.sendall(msg.encode())
            except Exception:
                break

        buf = b""
        while not self._reader_stop.is_set():
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._handle_ipc_line(line)
            except socket.timeout:
                continue
            except Exception:
                break

        try:
            sock.close()
        except Exception:
            pass

    def _handle_ipc_line(self, line: bytes) -> None:
        try:
            msg = json.loads(line)
        except Exception:
            return
        if msg.get("event") != "property-change":
            return
        name = msg.get("name", "")
        value = msg.get("data")

        with self._state_lock:
            if name == "time-pos" and isinstance(value, (int, float)):
                self._state.position = float(value)
            elif name == "duration" and isinstance(value, (int, float)):
                self._state.duration = float(value)
            elif name == "pause" and isinstance(value, bool):
                self._state.paused = value
            elif name == "volume" and isinstance(value, (int, float)):
                self._state.volume = int(value)
            elif name == "media-title" and isinstance(value, str):
                self._state.title = value

        # SponsorBlock auto-skip — runs on every time-pos tick
        if name == "time-pos" and isinstance(value, (int, float)):
            self._check_sponsorblock(float(value))

        event = PropertyEvent(name=name, value=value)
        for cb in list(self._on_property_cbs):
            try:
                cb(event)
            except Exception:
                pass

    def _check_sponsorblock(self, position: float) -> None:
        """If position falls inside a SponsorBlock segment, seek past it."""
        with self._sb_lock:
            if not self._sb_enabled or not self._sb_segments:
                return
            for idx, seg in enumerate(self._sb_segments):
                if idx in self._sb_skipped:
                    continue
                start: float = seg.get("start", -1)
                end: float = seg.get("end", -1)
                # Trigger when we enter the segment (within 0.5s of start)
                if start <= position < end and position >= start - 0.5:
                    self._sb_skipped.add(idx)
                    skip_to = end + 0.1
                    logger.debug(
                        "SponsorBlock: skipping %s [%.1f → %.1f]",
                        seg.get("category", "?"), start, end,
                    )
                    # Schedule the seek on a tiny thread to avoid deadlock
                    # (we're inside the socket reader thread here)
                    threading.Thread(
                        target=self._sb_seek,
                        args=(skip_to, seg),
                        daemon=True,
                        name="sb-skip",
                    ).start()
                    break

    def _sb_seek(self, skip_to: float, segment: dict) -> None:
        """Seek past a SponsorBlock segment and fire on_skip callbacks."""
        time.sleep(0.05)  # tiny buffer so mpv is ready for the seek
        self._send(["seek", skip_to, "absolute"])
        for cb in list(self._on_skip_cbs):
            try:
                cb(segment)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # IPC commands
    # ------------------------------------------------------------------

    def _send(self, command: list) -> dict | None:
        """Send a JSON command over the IPC socket.  Thread-safe."""
        if not self._sock_path.exists():
            return None
        try:
            with self._cmd_lock:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect(str(self._sock_path))
                msg = json.dumps({"command": command}) + "\n"
                sock.sendall(msg.encode())
                resp = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
                    if b"\n" in resp:
                        break
                sock.close()
            return json.loads(resp.split(b"\n")[0])
        except Exception as exc:
            logger.debug("IPC send failed: %s", exc)
            return None

    def pause_toggle(self) -> None:
        self._send(["cycle", "pause"])

    def seek(self, secs: float) -> None:
        self._send(["seek", secs, "relative"])

    def seek_percent(self, pct: float) -> None:
        self._send(["seek", pct, "absolute-percent"])

    def set_volume(self, vol: int) -> None:
        vol = max(0, min(200, vol))
        self._send(["set_property", "volume", vol])

    def volume_up(self, step: int = 5) -> None:
        with self._state_lock:
            current = self._state.volume
        self.set_volume(current + step)

    def volume_down(self, step: int = 5) -> None:
        with self._state_lock:
            current = self._state.volume
        self.set_volume(max(0, current - step))

    def stop(self) -> None:
        """Stop playback and clean up."""
        if self._proc is not None:
            self._reader_stop.set()
            self._send(["quit"])
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        with self._state_lock:
            self._state.idle = True
            self._state.mode = None
        with self._sb_lock:
            self._sb_skipped = set()


# Module-level singleton — created once, reused across audio/video plays
_session: PlayerSession | None = None


def get_session() -> PlayerSession:
    global _session
    if _session is None:
        _session = PlayerSession()
    return _session
