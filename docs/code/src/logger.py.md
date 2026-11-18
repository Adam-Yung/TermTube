# src/logger.py

Process-wide logger named `termtube`. Decisions: [docs/decisions/logging.md](../../decisions/logging.md).

## Invariants

- Without `--debug`, `setup()` sets the level to `CRITICAL + 1` and attaches no handler. Every `logger.*` call returns after the level check, before any formatting.
- Nothing ever goes to stderr: Textual owns the terminal and stray writes corrupt the frame. Sinks are the log file `<tmp>/TermTube/<YYYYmmdd_HHMMSS>.log` and the in-app debug window.
- `propagate = False` keeps records out of the root logger (and anything else that configured it).
- `--level ALL` means DEBUG.

## Interface

- `register_tui_sink(cb)`: `cb(levelname, message)` runs in whichever thread logged. The callback must marshal to the UI thread (`app.call_from_thread`). Registered by `tui/screens/mixins/debug_log.py`.
- `file_only(...)` tags the record so `_TUIHandler` skips it. Used when a screen already drew a styled line in the debug window.
- `stage(name)` logs a startup milestone once per name (`config loaded`, `first paint`, `first rows`, `stash shown`, `cookie jar ready`) with the delta since the previous stage and the time since `logger` was imported. Reading the log: [startup-debugging](../../guides/startup-debugging.md). It returns before any work when `--debug` is off.
- `main.py` calls `setup` once, then prints `log_file()` on exit when `--debug` is set.

## Limits

- The log directory goes through `plat.private_dir` (0700, owner and symlink checked); if it is refused the file is not written, like any other `OSError`.
- A failure to open the log file (`OSError`) is swallowed: the TUI sink still works, the file is silently missing.
- `redact` and `_RedactFilter` (on both handlers) strip URL query strings (signed stream URLs), cookie/token/SAPISID/Authorization values and anything past 2000 characters from every message and traceback; yt-dlp errors embed URLs. Call sites need no care.
- `setup` is safe to call again (tests): it removes existing handlers first.
