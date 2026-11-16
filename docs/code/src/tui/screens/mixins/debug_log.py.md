# src/tui/screens/mixins/debug_log.py

Ctrl+D panel (`RichLog#debug-log`) that mirrors the `--debug` logger. Registered as a sink with `logger.register_tui_sink` only when debug is on; otherwise the panel shows how to enable it.

- `_on_log_record` runs on whatever thread logged. It hops to the UI thread with `call_from_thread` and swallows errors, because a log call must never raise into the caller (the app may not be running yet or any more).
- `_write_log_record` escapes `[` in messages; log text containing brackets (URLs, dict reprs) would otherwise be parsed as Rich markup.
- `_log(msg)` takes Rich markup, writes it to the panel and its plain text (`_MARKUP` stripped) to the log file via `logger.file_only`. It is a no-op without `--debug`. Other mixins call it for user-visible progress lines.

Logging design: `docs/decisions/logging.md`.
