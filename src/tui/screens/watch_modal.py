"""WatchModal — in-TUI video player popup with progress tracking."""

from __future__ import annotations

import os
import subprocess

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static


def _fmt_secs(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


class WatchModal(ModalScreen[bool]):
    """
    Video watch screen: launches mpv (with video visible), shows a live progress
    bar in the TUI, and handles keyboard seek/pause/stop via IPC.
    """

    BINDINGS = [
        Binding("space",  "pause_toggle",  "Pause/Resume", show=True),
        Binding("h",      "seek_back",     "−5s",          show=True),
        Binding("l",      "seek_fwd",      "+5s",          show=True),
        Binding("H",      "seek_back_big", "−10s",         show=False),
        Binding("L",      "seek_fwd_big",  "+10s",         show=False),
        Binding("left",   "seek_back",     "−5s",          show=False),
        Binding("right",  "seek_fwd",      "+5s",          show=False),
        Binding("0",      "seek_pct_0",    "0%",           show=False),
        Binding("1",      "seek_pct_10",   "10%",          show=False),
        Binding("2",      "seek_pct_20",   "20%",          show=False),
        Binding("3",      "seek_pct_30",   "30%",          show=False),
        Binding("4",      "seek_pct_40",   "40%",          show=False),
        Binding("5",      "seek_pct_50",   "50%",          show=False),
        Binding("6",      "seek_pct_60",   "60%",          show=False),
        Binding("7",      "seek_pct_70",   "70%",          show=False),
        Binding("8",      "seek_pct_80",   "80%",          show=False),
        Binding("9",      "seek_pct_90",   "90%",          show=False),
        Binding("q",      "stop",          "Stop",         show=True),
        Binding("escape", "stop",          "Stop",         show=False),
    ]

    _SOCKET = "/tmp/termtube-mpv-video.sock"

    def __init__(self, entry: dict, *, ytdl_format: str = "") -> None:
        super().__init__()
        self._entry = entry
        self._ytdl_format = ytdl_format
        self._proc: subprocess.Popen | None = None  # type: ignore[type-arg]
        self._stopped = False

    def compose(self) -> ComposeResult:
        title = self._entry.get("title") or "Unknown"
        channel = self._entry.get("uploader") or self._entry.get("channel") or ""
        with Vertical(id="watch-dialog"):
            yield Static("📺  Now playing in mpv", id="np-header")
            yield Static(f"[bold white]{title}[/bold white]", id="np-title", markup=True)
            if channel:
                yield Static(channel, id="np-channel")
            yield ProgressBar(total=1000, show_eta=False, id="np-progress")
            yield Static("Loading…", id="np-time")
            yield Static(
                "[dim]space[/dim] pause  "
                "[dim]h/l[/dim] ±5s  "
                "[dim]H/L[/dim] ±10s  "
                "[dim]0–9[/dim] seek%  "
                "[dim]q[/dim] stop",
                id="np-hint",
                markup=True,
            )

    def on_mount(self) -> None:
        self._launch_video()
        self.set_interval(0.5, self._poll_mpv)

    # ── Background mpv launcher ───────────────────────────────────────────────

    @work(thread=True, exclusive=True, group="video_player")
    def _launch_video(self) -> None:
        from src import player as player_mod

        vid = self._entry.get("id", "")
        if vid and hasattr(self.app, "cache") and hasattr(self.app.cache, "suppress_video"):
            self.app.cache.suppress_video(vid)

        url = (
            self._entry.get("_local_path")
            or f"https://www.youtube.com/watch?v={vid}"
        )
        title = self._entry.get("title", "")

        config = getattr(self.app, "config", None)
        cookie_args = config.cookie_args if config else []

        input_conf = player_mod._write_input_conf()
        cmd = [
            "mpv",
            f"--input-conf={input_conf}",
            f"--input-ipc-server={self._SOCKET}",
            "--no-terminal",
            "--really-quiet",
            "--msg-level=all=no",
        ]
        if title:
            cmd += [f"--title={title}"]
        if self._ytdl_format:
            cmd += [f"--ytdl-format={self._ytdl_format}"]
        ytdl_raw = player_mod._cookie_args_to_ytdl_raw(cookie_args)
        if ytdl_raw:
            cmd += [f"--ytdl-raw-options={ytdl_raw}"]
        cmd += ["--", url]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.app.call_from_thread(
                self.app.notify,
                "mpv not found — install with: brew install mpv",
                severity="error",
            )
            self.app.call_from_thread(self.dismiss, False)
            return
        except OSError as exc:
            self.app.call_from_thread(
                self.app.notify, f"Failed to launch mpv: {exc}", severity="error"
            )
            self.app.call_from_thread(self.dismiss, False)
            return

        try:
            self._proc.wait()
        finally:
            for path in (input_conf, self._SOCKET):
                try:
                    os.unlink(path)
                except OSError:
                    pass

        # Write history only after successful playback ends
        from src import history
        history.add(self._entry)

        if not self._stopped:
            self.app.call_from_thread(self.dismiss, True)
            if title:
                self.app.call_from_thread(
                    self.app.notify, f"✓ Finished: {title[:50]}", timeout=4
                )

    # ── IPC polling ───────────────────────────────────────────────────────────

    def _poll_mpv(self) -> None:
        # Auto-dismiss if the user manually closes the external mpv window
        if self._proc and self._proc.poll() is not None:
            if not self._stopped:
                self._stopped = True
                self.dismiss(True)
            return

        from src.player import poll_audio_properties

        pos, dur, paused = poll_audio_properties(socket_path=self._SOCKET)
        if pos is not None and dur and float(dur) > 0:
            frac = min(float(pos) / float(dur), 1.0)
            try:
                self.query_one("#np-progress", ProgressBar).update(
                    progress=int(frac * 1000)
                )
                pause_indicator = "  ⏸ paused" if paused else ""
                self.query_one("#np-time", Static).update(
                    f"{_fmt_secs(float(pos))}  /  {_fmt_secs(float(dur))}{pause_indicator}"
                )
            except Exception:
                pass

    # ── IPC helper ────────────────────────────────────────────────────────────

    def _ipc(self, cmd: list) -> None:
        from src.player import send_ipc_command
        send_ipc_command({"command": cmd}, socket_path=self._SOCKET)

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_pause_toggle(self) -> None:
        self._ipc(["cycle", "pause"])

    def action_seek_back(self) -> None:
        self._ipc(["seek", -5, "relative"])

    def action_seek_fwd(self) -> None:
        self._ipc(["seek", 5, "relative"])

    def action_seek_back_big(self) -> None:
        self._ipc(["seek", -10, "relative"])

    def action_seek_fwd_big(self) -> None:
        self._ipc(["seek", 10, "relative"])

    def _seek_pct(self, pct: int) -> None:
        self._ipc(["seek", pct, "absolute-percent"])

    def action_seek_pct_0(self)  -> None: self._seek_pct(0)
    def action_seek_pct_10(self) -> None: self._seek_pct(10)
    def action_seek_pct_20(self) -> None: self._seek_pct(20)
    def action_seek_pct_30(self) -> None: self._seek_pct(30)
    def action_seek_pct_40(self) -> None: self._seek_pct(40)
    def action_seek_pct_50(self) -> None: self._seek_pct(50)
    def action_seek_pct_60(self) -> None: self._seek_pct(60)
    def action_seek_pct_70(self) -> None: self._seek_pct(70)
    def action_seek_pct_80(self) -> None: self._seek_pct(80)
    def action_seek_pct_90(self) -> None: self._seek_pct(90)

    def action_stop(self) -> None:
        self._stopped = True
        self._ipc(["quit"])
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self.dismiss(False)
