"""ActionBar — bottom-right panel with two modes: action hints and now-playing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


_ACTIONS_ROW1 = (
    "  [bold #ff6666]⏎[/bold #ff6666] [dim]Video actions[/dim]   "
    "[bold #ff6666]w[/bold #ff6666] [dim]Watch[/dim]   "
    "[bold #ff6666]l[/bold #ff6666] [dim]Listen[/dim]   "
    "[bold #ff6666]d[/bold #ff6666] [dim]DL Video[/dim]   "
    "[bold #ff6666]a[/bold #ff6666] [dim]DL Audio[/dim]"
)
_ACTIONS_ROW2 = (
    "  [bold #ff6666]s[/bold #ff6666] [dim]Subscribe[/dim]   "
    "[bold #ff6666]p[/bold #ff6666] [dim]Playlist[/dim]   "
    "[bold #ff6666]b[/bold #ff6666] [dim]Browser[/dim]   "
    "[bold #ff6666]r[/bold #ff6666] [dim]Refresh[/dim]   "
    "[bold #ff6666]?[/bold #ff6666] [dim]Help[/dim]"
)

_NP_KEYS = (
    "[dim]spc[/dim] pause  "
    "[bold #ff6666]h[/bold #ff6666][dim]/[/dim][bold #ff6666]l[/bold #ff6666] [dim]±5s[/dim]  "
    "[bold #ff6666]H[/bold #ff6666][dim]/[/dim][bold #ff6666]L[/bold #ff6666] [dim]±10s[/dim]  "
    "[dim]0–9[/dim] seek%  "
    "[bold #ff6666]s[/bold #ff6666] [dim]stop[/dim]"
)


def _fmt_secs(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m2 = divmod(m, 60)
    if h:
        return f"{h}:{m2:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _text_bar(pos: float, dur: float, width: int) -> str:
    """Render a Unicode block progress bar of the given character width."""
    width = max(4, width)
    if dur <= 0:
        return f"[#2a2a40]{'─' * width}[/#2a2a40]"
    frac = min(pos / dur, 1.0)
    filled = int(frac * width)
    empty = width - filled
    return (
        f"[#6666ff]{'█' * filled}[/#6666ff]"
        f"[#2a2a40]{'░' * empty}[/#2a2a40]"
    )


class ActionBar(Widget):
    """
    Dual-mode bottom panel:
      • Actions mode  — keyboard shortcut grid
      • Player mode   — embedded now-playing bar with full-width text progress bar
    """

    _HEIGHT_ACTIONS = 7   # border(2) + margin-top(1) + row1(1) + row2(1) + slack(2)
    _HEIGHT_PLAYER  = 10  # border(2) + margin-top(1) + title(1) + gap(1) + bar(1) + gap(1) + time(1) + keys(1) + slack(1)

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
    #ab-row1 { margin-top: 1; color: #cccccc; }
    #ab-row2 { color: #888888; }
    #np-title-line { margin-top: 1; color: #ffffff; }
    #np-bar-text   { margin-top: 1; color: #6666ff; }
    #np-time-line  { color: #666666; }
    #np-keys       { margin-top: 1; color: #888888; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pos: float = 0.0
        self._dur: float = 0.0
        self._paused: bool = False
        self._title: str = ""
        self._channel: str = ""
        self._playing: bool = False

    def compose(self) -> ComposeResult:
        # ── Actions mode ──────────────────────────────────────────────────────
        yield Static(_ACTIONS_ROW1, id="ab-row1", markup=True)
        yield Static(_ACTIONS_ROW2, id="ab-row2", markup=True)
        # ── Player mode (initially hidden) ────────────────────────────────────
        yield Static("", id="np-title-line", markup=True)
        yield Static("", id="np-bar-text",   markup=True)   # text-based bar
        yield Static("", id="np-time-line",  markup=True)
        yield Static(_NP_KEYS, id="np-keys", markup=True)

    def on_mount(self) -> None:
        self.border_title = "Actions"
        self._set_mode_actions()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_actions_mode(self) -> None:
        self._playing = False
        self._set_mode_actions()

    def set_player_mode(self, entry: dict) -> None:
        self._title   = (entry.get("title") or "Unknown")[:52]
        self._channel = entry.get("uploader") or entry.get("channel") or ""
        self._playing = True
        self._paused  = False
        self._pos = 0.0
        self._dur = 0.0
        self._set_mode_player()

    def update_progress(self, pos: float, dur: float, paused: bool) -> None:
        if not self._playing:
            return
        self._pos    = pos
        self._dur    = dur
        self._paused = paused
        self._refresh_player()

    # ── Private ───────────────────────────────────────────────────────────────

    def _set_mode_actions(self) -> None:
        self.styles.height = self._HEIGHT_ACTIONS
        self.border_title = "Actions"
        self.query_one("#ab-row1").display       = True
        self.query_one("#ab-row2").display       = True
        self.query_one("#np-title-line").display = False
        self.query_one("#np-bar-text").display   = False
        self.query_one("#np-time-line").display  = False
        self.query_one("#np-keys").display       = False

    def _set_mode_player(self) -> None:
        self.styles.height = self._HEIGHT_PLAYER
        self.border_title = "Now Playing"
        self.query_one("#ab-row1").display       = False
        self.query_one("#ab-row2").display       = False
        self.query_one("#np-title-line").display = True
        self.query_one("#np-bar-text").display   = True
        self.query_one("#np-time-line").display  = True
        self.query_one("#np-keys").display       = True
        self._refresh_player()

    def _refresh_player(self) -> None:
        # Title line
        paused_tag = "  [dim bold][PAUSED][/dim bold]" if self._paused else ""
        chan = f"  [dim]· {self._channel}[/dim]" if self._channel else ""
        self.query_one("#np-title-line", Static).update(
            f"[bold white]🎵  {self._title}[/bold white]{chan}{paused_tag}"
        )

        # Full-width text bar.
        # Available inner width = widget width - 2 (border) - 2 (padding L+R).
        inner_w = max(8, (self.size.width or 60) - 4)
        self.query_one("#np-bar-text", Static).update(
            _text_bar(self._pos, self._dur, inner_w)
        )

        # Time
        if self._dur > 0:
            elapsed  = _fmt_secs(self._pos)
            total    = _fmt_secs(self._dur)
            pct      = int(min(self._pos / self._dur, 1.0) * 100)
            time_str = f"{elapsed}  /  {total}  ({pct}%)"
        else:
            time_str = "Loading…"
        self.query_one("#np-time-line", Static).update(f"[dim]{time_str}[/dim]")
