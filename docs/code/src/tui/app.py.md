# src/tui/app.py

`TermTubeApp`: the Textual app root. It holds `config` and `cache` for every widget, applies the theme class, pushes `MainScreen`, and
owns startup warmup and shutdown cleanup. It sets `HORIZONTAL_BREAKPOINTS` from `layout.py` so screens carry `-narrow` / `-wide`. Everything else lives in screens and mixins (`docs/features/architecture.md`).

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
path gets there first. Housekeeping pins playlist videos before pruning; failures are logged, never raised. It prunes thumbnails (7 days, 300), video metadata (3 days, 400), search feeds (14 days, 50), rendered ANSI thumbnails (7 days, 600) and SponsorBlock segment files (past the 24 h TTL, 300).

## Limits

- Tests must patch the exit path and set `browser: none`, or the warmup thread reads the real browser profile.

## Notifications

`notify` is overridden to escape its message (`fmt.escape_markup`): every notice in the app is plain text and many carry video titles with `[brackets]`, which Textual would otherwise parse as markup. Pass `markup=False` to skip the escape. Look: `docs/decisions/ui.md`.

`_store_save_failed` is the `store.set_failure_hook` callback: an error notice when a JSON store cannot write (direct on the UI thread, `call_from_thread` otherwise); cleared in `on_unmount`.

`call_ui` is `call_from_thread` for worker threads that may outlive the app (loaders, the SponsorBlock fetch, channel workers): once the app is closing the call is dropped instead of raising `RuntimeError` on a closed loop.
