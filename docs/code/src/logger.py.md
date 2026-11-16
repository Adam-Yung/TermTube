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
- `main.py` calls `setup` once, then prints `log_file()` on exit when `--debug` is set.

## Limits

- A failure to open the log file (`OSError`) is swallowed: the TUI sink still works, the file is silently missing.
- `setup` is safe to call again (tests): it removes existing handlers first.
