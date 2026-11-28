# Debugging slow startup and slow playback

> Verified: 2026-11-28 · Sources: `src/logger.py`, `src/streams.py`, `src/player.py`, `src/tui/audio_launch.py`, `src/deps.py`

Run these on the slow machine and keep the output. yt-dlp is a Python package in the app's venv; mpv is the managed binary.

## Binary and resolve times

```bash
APP=~/.local/share/TermTube
time ~/.local/termtube-deps/bin/mpv --no-config --version
time ~/.local/termtube-deps/bin/mpv --no-config --no-video --ao=null av://lavfi:sine=d=1
time "$APP/.venv/bin/python" -m yt_dlp -g -f ba/b "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

A slow second run of mpv points at antivirus scanning. The last command contacts YouTube: run it once, not in a loop. It takes about 1 to 3 s
([benchmarks.md](benchmarks.md)) and uses no cookies, as the app does.

## App startup stages

`termtube --debug` logs one line per startup milestone, each once: `startup stage <name>: +<ms since previous stage> (<ms since start> ms since start)`.
Stages: `config loaded`, `first paint` (main screen mounted and refreshed), `stash shown` (Home stash rendered), `first rows` (first list page on
screen), `cookie jar ready` (browser cookies extracted). The log is in `<temp>/TermTube/`; find the lines with `grep "startup stage"`. The clock
starts when `src.logger` is imported, so interpreter start and the `src.main` import chain are not counted; compare with `time termtube --version`.

## mpv's own log (audio)

With `--debug`, the audio player also starts mpv with `--msg-level=all=info --log-file=<log dir>/<timestamp>-mpv.log`, next to the app's debug
log. Without it mpv only prints errors, and since mpv's terminal input is off (`--no-input-terminal`, `stdin` closed) a failure can read
"exit code N" with an empty stderr when the cause is a warning-level condition such as a missing audio device. The real-app CI job
(`scripts/e2e-local.py --debug-log`) prints the app log when a step fails.
