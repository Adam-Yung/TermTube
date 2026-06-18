"""ActionBar — bottom-right panel with two modes: action hints and now-playing."""

from __future__ import annotations

import math

from rich.table import Table
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from src.sponsorblock import Segment

_WAVE_CHARS = "▁▂▃▄▅▆▇█"
_WAVE_SPEED = 0.4


def _fmt_secs(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m2 = divmod(m, 60)
    if h:
        return f"{h}:{m2:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _queue_hint(queue_len: int, hide_e: bool = False, color: str = "#ff6666") -> str:
    e_part = "" if hide_e else f"[bold {color}]e[/bold {color}] [dim]add to queue[/dim]"
    skip_part = (
        f"[bold {color}]>[/bold {color}] [dim]skip to next  ({queue_len} queued)[/dim]"
        if queue_len > 0
        else ""
    )
    parts = [p for p in (e_part, skip_part) if p]
    return "  ".join(parts)


class ActionBar(Widget):
    """
    Dual-mode bottom panel:
      • Actions mode  — keyboard shortcut grid
      • Player mode   — embedded now-playing bar with text progress and queue hints
    """

    _HEIGHT_ACTIONS = 7
    _HEIGHT_PLAYER = 11

    DEFAULT_CSS = """
    ActionBar {
        height: 7;
        background: #0d0d14;
        border: solid #2a2a2a;
        border-title-color: #555555;
        border-title-style: dim;
        margin: 0 1 1 1;
        padding: 0 1;
    }
    ActionBar > Static { height: 1; }

    #ab-actions { height: 2; margin-top: 1; margin-left: 2; }

    #np-title-line { margin-top: 1; color: #ffffff; }
    #np-bar-text   { margin-top: 1; }
    #np-time-line  { color: #666666; }
    #np-keys       { margin-top: 1; color: #888888; }
    #np-queue-line { color: #888888; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pos: float = 0.0
        self._dur: float = 0.0
        self._paused: bool = False
        self._title: str = ""
        self._channel: str = ""
        self._playing: bool = False
        self._queue_len: int = 0
        self._segments: list[Segment] = []
        self._wave_frame: int = 0
        self._wave_timer = None
        # Pre-computed segment column map: list[bool] of length == last rendered width.
        # Invalidated when _segments or _dur changes.
        self._segment_cols: list[bool] = []
        self._segment_cols_width: int = 0
        self._segment_cols_dur: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static(id="ab-actions")
        yield Static("", id="np-title-line", markup=True)
        yield Static("", id="np-bar-text", markup=True)
        yield Static("", id="np-time-line", markup=True)
        yield Static("", id="np-keys", markup=True)
        yield Static("", id="np-queue-line", markup=True)

    def on_mount(self) -> None:
        self.border_title = "Actions"
        self.query_one("#ab-actions", Static).update(self._get_actions_table())
        self._update_np_keys()
        self._set_mode_actions()

    # ── Theme Resolvers ───────────────────────────────────────────────────────

    def _get_theme_color(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"
        return {
            "crimson": "#ff6666",
            "amber": "#e8820c",
            "ocean": "#0ea5e9",
            "midnight": "#a855f7",
        }.get(theme, "#ff6666")

    def _get_progress_color(self) -> str:
        try:
            theme = self.app.config.theme
        except Exception:
            theme = "crimson"
        return {
            "crimson": "#6666ff",
            "amber": "#e8820c",
            "ocean": "#0ea5e9",
            "midnight": "#a855f7",
        }.get(theme, "#6666ff")

    # ── UI Builders ───────────────────────────────────────────────────────────

    def _get_actions_table(self) -> Table:
        table = Table.grid(padding=(0, 4))
        for _ in range(5):
            table.add_column()

        color = self._get_theme_color()

        def r1(k: str, v: str) -> str:
            return f"[#cccccc][bold {color}]{k}[/bold {color}] [dim]{v}[/dim][/#cccccc]"

        def r2(k: str, v: str) -> str:
            return f"[#888888][bold {color}]{k}[/bold {color}] [dim]{v}[/dim][/#888888]"

        table.add_row(
            r1("⏎", "Video actions"),
            r1("w", "Watch"),
            r1("l", "Listen"),
            r1("d", "Download"),
            r1("c", "Channel"),
        )
        table.add_row(
            r2("y", "Copy URL"),
            r2("s", "Subscribe"),
            r2("p", "Playlist"),
            r2("b", "Browser"),
            r2("r", "Refresh"),
        )

        return table

    def _build_segment_cols(self, width: int, dur: float) -> list[bool]:
        """Pre-compute which columns fall inside a SponsorBlock segment."""
        cols: list[bool] = []
        for col in range(width):
            t = (col / width) * dur
            cols.append(any(s.start <= t < s.end for s in self._segments))
        return cols

    def _get_segment_cols(self, width: int, dur: float) -> list[bool]:
        """Return cached segment-column map, rebuilding only when inputs change."""
        if (
            self._segment_cols_width != width
            or self._segment_cols_dur != dur
            or len(self._segment_cols) != width
        ):
            self._segment_cols = self._build_segment_cols(width, dur)
            self._segment_cols_width = width
            self._segment_cols_dur = dur
        return self._segment_cols

    def _text_bar(self, pos: float, dur: float, width: int) -> str:
        width = max(4, width)
        if dur <= 0:
            return self._wave_bar(width)
        frac = min(pos / dur, 1.0)
        filled = int(frac * width)
        color = self._get_progress_color()
        sponsor_color = "#22c55e"
        sponsor_dim = "#166534"

        if not self._segments:
            empty = width - filled
            return f"[{color}]{'█' * filled}[/{color}][#2a2a40]{'░' * empty}[/#2a2a40]"

        seg_cols = self._get_segment_cols(width, dur)
        parts: list[str] = []
        for col in range(width):
            in_segment = seg_cols[col]
            if col < filled:
                c = sponsor_color if in_segment else color
                parts.append(f"[{c}]█[/{c}]")
            else:
                c = sponsor_dim if in_segment else "#2a2a40"
                parts.append(f"[{c}]░[/{c}]")
        return "".join(parts)

    def _update_np_keys(self) -> None:
        color = self._get_theme_color()
        keys = (
            f"[bold {color}]⎵[/bold {color}] [dim]pause[/dim]  "
            f"[bold {color}]h[/bold {color}][dim]/[/dim][bold {color}]l[/bold {color}] [dim]±5s[/dim]  "
            f"[bold {color}]H[/bold {color}][dim]/[/dim][bold {color}]L[/bold {color}] [dim]±10s[/dim]  "
            f"[bold {color}]0[/bold {color}][dim]–[/dim][bold {color}]9[/bold {color}] [dim]seek%[/dim]  "
            f"[bold {color}]s[/bold {color}] [dim]stop[/dim]"
        )
        self.query_one("#np-keys", Static).update(keys)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_segments(self, segments: list[Segment]) -> None:
        """Set SponsorBlock segments for progress bar overlay."""
        self._segments = segments
        self._segment_cols = []  # invalidate cache

    def refresh_theme(self) -> None:
        """Re-render all Rich-markup elements after a theme change."""
        self.query_one("#ab-actions", Static).update(self._get_actions_table())
        self._update_np_keys()
        if self._playing:
            self._refresh_player()

    def set_actions_mode(self) -> None:
        self._playing = False
        self._queue_len = 0
        self._segments = []
        self._segment_cols = []
        if self._wave_timer is not None:
            self._wave_timer.stop()
            self._wave_timer = None
        self._set_mode_actions()

    def set_player_mode(self, entry: dict, queue_len: int = 0) -> None:
        import time
        self._title = (entry.get("title") or "Unknown")[:52]
        self._channel = entry.get("uploader") or entry.get("channel") or ""
        self._playing = True
        self._paused = False
        self._pos = 0.0
        self._dur = 0.0
        self._queue_len = queue_len
        self._buffering_since = time.monotonic()
        self._wave_frame = 0
        if self._wave_timer is None:
            self._wave_timer = self.set_interval(0.2, self._animate_wave)
        self._set_mode_player()

    def update_progress(self, pos: float, dur: float, paused: bool) -> None:
        if not self._playing:
            return
        if dur > 0 and self._wave_timer is not None:
            self._wave_timer.stop()
            self._wave_timer = None
        # Skip redundant redraws: ignore sub-quarter-second position drift while
        # pause state is unchanged — avoids ~2 renders/sec when paused.
        if (
            paused == self._paused
            and abs(pos - self._pos) < 0.25
            and abs(dur - self._dur) < 1.0
        ):
            return
        self._pos = pos
        self._dur = dur
        self._paused = paused
        self._refresh_player()

    def update_queue_hint(self, queue_len: int, *, hide_e: bool = False) -> None:
        if not self._playing:
            return
        self._queue_len = queue_len
        self.query_one("#np-queue-line", Static).update(
            _queue_hint(queue_len, hide_e=hide_e, color=self._get_theme_color())
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _animate_wave(self) -> None:
        """Animate the waveform while buffering (dur == 0)."""
        if self._dur > 0:
            if self._wave_timer is not None:
                self._wave_timer.stop()
                self._wave_timer = None
            return
        if not self._playing:
            if self._wave_timer is not None:
                self._wave_timer.stop()
                self._wave_timer = None
            return
        self._wave_frame += 1
        self._refresh_player()

    def _wave_bar(self, width: int) -> str:
        """Generate an animated sine-wave equalizer bar."""
        color = self._get_progress_color()
        chars = []
        for col in range(width):
            phase = (col + self._wave_frame * 1.2) * 0.3
            val = (math.sin(phase) + math.sin(phase * 1.7 + 1.0) + 2.0) / 4.0
            idx = int(val * (len(_WAVE_CHARS) - 1))
            chars.append(_WAVE_CHARS[idx])
        wave_text = "".join(chars)
        return f"[{color}]{wave_text}[/{color}]"

    def _set_mode_actions(self) -> None:
        self.styles.height = self._HEIGHT_ACTIONS
        self.border_title = "Actions"
        self.query_one("#ab-actions").display = True
        self.query_one("#np-title-line").display = False
        self.query_one("#np-bar-text").display = False
        self.query_one("#np-time-line").display = False
        self.query_one("#np-keys").display = False
        self.query_one("#np-queue-line").display = False

    def _set_mode_player(self) -> None:
        self.styles.height = self._HEIGHT_PLAYER
        self.border_title = "Now Playing"
        self.query_one("#ab-actions").display = False
        self.query_one("#np-title-line").display = True
        self.query_one("#np-bar-text").display = True
        self.query_one("#np-time-line").display = True
        self.query_one("#np-keys").display = True
        self.query_one("#np-queue-line").display = True
        self.query_one("#np-queue-line", Static).update("")
        self._update_np_keys()
        self._refresh_player()

    def _refresh_player(self) -> None:
        paused_tag = "  [dim bold][PAUSED][/dim bold]" if self._paused else ""
        chan = f"  [dim]· {self._channel}[/dim]" if self._channel else ""
        self.query_one("#np-title-line", Static).update(
            f"[bold white]🎵  {self._title}[/bold white]{chan}{paused_tag}"
        )

        inner_w = max(8, (self.size.width or 60) - 4)
        self.query_one("#np-bar-text", Static).update(
            self._text_bar(self._pos, self._dur, inner_w)
        )

        if self._dur > 0:
            elapsed = _fmt_secs(self._pos)
            total = _fmt_secs(self._dur)
            pct = int(min(self._pos / self._dur, 1.0) * 100)
            time_str = f"{elapsed}  /  {total}  ({pct}%)"
        else:
            import time
            wait_s = int(time.monotonic() - getattr(self, "_buffering_since", time.monotonic()))
            time_str = f"Buffering… ({wait_s}s)" if wait_s > 0 else "Buffering…"
        self.query_one("#np-time-line", Static).update(f"[dim]{time_str}[/dim]")
