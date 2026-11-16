# Logging

The `--debug` and `--level` flags, log destinations, and the TUI log sink.

## 2026-05-03 — `--debug` makes logging fully silent, not just suppressed

Without `--debug`, `logger.setup()` sets the logger level above `CRITICAL` and attaches no handlers. Python's logging short-circuits in `Logger.isEnabledFor()` before any string formatting, so each `logger.debug(...)` call costs one attribute lookup and one integer comparison. No file opens, nothing goes to stderr, and nothing appears in the in-app debug window. This is faster (no formatting cost) and keeps error noise out of a quiet TUI.

## 2026-05-03 — Nothing is written to stderr, even in `--debug`

Textual owns stdout and stderr while the app runs. A stray write corrupts the rendered frame (cursor jumps, ghost characters, a broken alt-screen). The original logger had a `StreamHandler(sys.stderr)` for development convenience. It produced visible glitches as soon as anything logged from a worker thread. The file handler at `$TMPDIR/TermTube/<ts>.log` plus the in-app Ctrl+D window are enough and never collide with the renderer.

## 2026-05-03 — `--level` defaults to `ALL` (= DEBUG), not `INFO`

`--debug` is already opt-in. A user who passes it wants everything. An `INFO` default would silently drop the most useful records (cache hits, yt-dlp commands, mpv launches) as soon as someone enables debugging. `--level` exists for the rare noisy run that needs filtering down to warnings and errors. Passing `--level WARNING` for that costs little, and "everything is captured" is the default.

## 2026-05-03 — Custom `_TUIHandler` instead of routing logs through `MainScreen._log`

A logging handler is the natural seam for "send every log record somewhere additional". It works for any module that imports `logger` (cache, ytdlp, player, widgets), and those modules need no knowledge of Textual. The handler invokes a callback registered with `register_tui_sink`. The callback marshals to the UI thread (`app.call_from_thread`).

The `_termtube_skip_tui` record attribute, set by `logger.file_only`, lets `MainScreen._log` write rich markup directly to the RichLog and still persist a plain version to the file, without duplicating the line in the TUI.
