# src/tui/screens/mixins/debug_log.py

Ctrl+D panel (`RichLog#debug-log`) that mirrors the `--debug` logger. Registered as a sink with `logger.register_tui_sink` only when debug is on; otherwise the panel shows how to enable it.

- `_on_log_record` runs on whatever thread logged, **while the logging handler's lock is held**, so it only puts the record on a `queue.SimpleQueue` and returns. A UI timer (`_drain_log_queue`, every 0.2 s, at most 200 records per tick) writes them into the panel. It used to call `call_from_thread`, which blocks until the UI thread runs the callback: when the UI thread was itself logging and waiting for the handler lock, both waited forever (a frozen app right after "Audio start", seen intermittently in the Windows CI job that runs with `--debug`). `tests/tui/test_debug_log_deadlock.py` reproduces it (60 s hang without the fix).
- `_write_log_record` escapes `[` in messages; log text containing brackets (URLs, dict reprs) would otherwise be parsed as Rich markup.
- `_log(msg)` takes Rich markup, writes it to the panel and its plain text (`_MARKUP` stripped) to the log file via `logger.file_only`. It is a no-op without `--debug`. Other mixins call it for user-visible progress lines.

Logging design: `docs/decisions/logging.md`.
