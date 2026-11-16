# src/tui/app.py

`TermTubeApp`: the Textual app root. It holds `config` and `cache` for every widget, applies the theme class, pushes `MainScreen`, and
owns startup warmup and shutdown cleanup. Everything else lives in screens and mixins (`docs/features/architecture.md`).

## Startup (`on_mount`)

1. `plat.reap_orphans()` removes stale mpv sockets and kills mpv processes left by a crashed run.
2. Theme: any theme except `crimson` becomes a `theme-<name>` CSS class on the app. `crimson` is the base CSS.
3. A daemon thread warms yt-dlp's extractor registry. Cookies are not read here; the first home-feed or subscription fetch extracts them (5 to 15 s on a cold profile).
4. Housekeeping is deferred 60 s with `set_timer` so cache pruning does not compete with the first feed render for disk.

## Shutdown

`_atexit_cleanup` (kill every `ProcessRegistry` process, `ytdlp.cancel_all()`, only if `src.ytdlp` was ever imported) runs from both `on_unmount` and `atexit`. It is idempotent,
because a normal quit hits both. `main.py` adds signal handlers and `close_all_sockets`, described in
`docs/decisions/concurrency.md#2026-06-17--unified-process-registry-and-structured-shutdown`.

`on_unmount` then runs housekeeping synchronously if the timer never fired. `_housekeeping_done` makes it run once per process, whichever
path gets there first. Housekeeping pins playlist videos before pruning; failures are logged, never raised.

## Limits

- Tests must patch the exit path and set `browser: none`, or the warmup thread reads the real browser profile.
