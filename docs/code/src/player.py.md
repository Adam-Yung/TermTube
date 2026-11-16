# src/player.py

Launch helpers for mpv and the JSON IPC client used to control it. It owns the mpv executable lookup, the temporary `input.conf`, the
headless audio command line, and the two IPC transports. It owns the launch loop (`run_mpv_with_retries`) but not what a result means: screens spawn through it and map the outcome (`src/tui/audio_controller.py`, `src/tui/screens/watch_modal.py`).

Decisions: `docs/decisions/playback.md`, `docs/decisions/concurrency.md`.

## IPC transports

| | Unix (macOS, Linux) | Windows |
|---|---|---|
| Endpoint | Unix socket in a 0700 per-user dir (`plat._ipc_path`) | named pipe `\\.\pipe\termtube-mpv...` |
| Connection | persistent, pooled per path in `_persistent_sockets` | connect-per-call (`CreateFile`, then close) |
| Client | stdlib `socket` | `pywin32` (`win32file`, `win32pipe`), imported lazily |
| Missing client or endpoint | `None` socket, empty reply | `ImportError` or `pywintypes.error`, empty reply |

`IS_WINDOWS` selects the transport inside `_ipc_send_recv` and `poll_audio_properties`. Callers never branch on it. Every failure ends as an
empty reply, `None`, or `(None, None, False)`: a dead mpv is a normal state, not an exception.

Windows pipes are not pooled: each call opens and closes the handle, and `WaitNamedPipe` covers `ERROR_PIPE_BUSY` while mpv serves another
client.

## Threading rules for the socket pool

IPC runs from worker threads (`audio_poll` group polls every 0.5 s, seek and pause commands come from the UI thread) and the same mpv
socket is shared by all of them.

- `_persistent_lock` guards the `_persistent_sockets` dict only. It is never held across `send` or `recv`.
- `_get_ipc_lock(path)` returns one lock per socket path. Every send/recv exchange on that path runs under it. Without it, two threads
  interleave their writes on the single stream and read each other's replies.
- Lock order is per-path lock, then `_persistent_lock` (inside `_get_persistent_socket` and `_drop_persistent_socket`). Nothing takes them
  in the reverse order.
- A broken pipe, reset or EOF drops the pooled socket and retries once with a fresh connection. A second failure returns empty. A
  `socket.timeout` is not an error: the reply read stops and returns what arrived.
- `_drop_persistent_socket` also removes the path lock. A thread already holding the old lock keeps using that object, so a new thread may
  briefly hold a different lock for the same path. This is safe only because the dropped socket is closed, and the next exchange
  reconnects.
- `_ipc_locks` is bounded by `_IPC_LOCKS_MAX` and cleared when full. Audio sessions use a new socket path per session
  (`-2`, `-3` suffixes), so paths accumulate.
- `close_persistent_socket(path)` must be called when a track ends or mpv exits. Otherwise the next session on the same path would reuse a
  socket that points at a dead mpv. `close_all_sockets()` runs at app exit (`src/main.py`) and also deletes the temp input confs.

## Batched polling

`poll_audio_properties` asks for `time-pos`, `duration` and `pause` in one round trip, tagged with `request_id` 0 to 2. mpv also emits
unsolicited event lines on the same socket, so replies are matched by `request_id`, never by order. Unix reads until all three arrive or the
1 s socket timeout hits. Missing values come back as `None` (`paused` is `False`). Without `pywin32` the Windows path falls back to three
single `get_property` calls.

## Executable lookup (`mpv_exe`)

Order: the bundled mpv in `~/.local/termtube-deps/bin/`, then `PATH`, then (Windows only) mpv.net.

With `headless=True` on Windows only the TermTube-bundled `mpv.exe` or a `PATH` `mpv.exe` without an `mpvnet.exe` sibling qualifies. The
function returns `None` otherwise. Symptom of ignoring this: a visible mpv window pops up on every audio play, because mpv.net ignores
`--force-window=no`, and its install dir ships an `mpv.exe` stub that redirects to `mpvnet.exe`. See the 2026-05-16 entry in the playback
log.

## Input config

`write_input_conf` writes a temp `input.conf` (digits seek to percent, `h`/`l`/`H`/`L` and arrows seek, `q` quits) for the video player,
where mpv owns the keyboard. These are mpv's keys, separate from the TUI keymap in `src/tui/keymap.py`. Files are tracked in
`_temp_input_confs` and removed by `close_all_sockets`.

## Audio command

`audio_command` builds the headless command. With a pre-resolved `stream_url` it passes `--no-ytdl` and plays the URL directly. Without
one, mpv resolves `page_url` through its own yt-dlp hook, with `--ytdl-format` and cookie flags converted by `cookie_args_to_ytdl_raw`
(only `--key value` pairs convert; bare flags are dropped). `--msg-level=all=error` keeps stderr small enough to capture and summarise via
`friendly_mpv_error`, which maps known error text to a toast and truncates unknown text to 100 characters.

## Known limits

- The Windows paths have no automated test coverage; the Unix paths are covered by `src/tests/integration/test_mpv_ipc.py`.
- The IPC reply read on Unix returns once a newline arrives, so one extra queued event line can be left in the stream. Request-id matching
  makes the polling path immune. `send_ipc_command` returns the first parsed line, which can be an event rather than the reply if mpv
  emitted one just before.

## Launch loop

`run_mpv_with_retries(build_cmd, ...)` is the only place mpv is spawned and retried; the audio controller (`headless=True`, stderr captured) and `WatchModal` (`headless=False`, stderr discarded) share it and keep their own command builders. It returns an `MpvOutcome` instead of acting on it:

- `ok` (exit 0 or 4) and `killed` (exit 3, the stop key or a signal) are normal exits; the caller decides what each means (audio advances the queue on `ok` and says nothing on `killed`; video dismisses on both).
- Any other exit retries after 1 s, up to `MPV_MAX_ATTEMPTS` (3), then `failed` with the last exit code and stderr. `build_cmd(attempt)` is where a caller re-resolves an expired stream URL for attempts after the first.
- mpv's stdin is `DEVNULL` and the audio command uses `--no-input-terminal`, not `--no-terminal`: mpv must not read the TUI's keystrokes, but its error messages (`--msg-level=all=error`) must reach the captured stderr. With `--no-terminal` a Windows failure read "exit code 2, no stderr output" and the cause was invisible.
- Captured stderr is decoded as UTF-8 with `errors="replace"`, never the locale codec: on Windows without UTF-8 mode (cp1252) a title containing `ā` made `communicate()` raise and left `returncode` unset.
- `stale` is returned when `is_stale()` is true before a launch or after an exit; the process may have run, and the caller discards the result.
- `launch_error` (mpv missing, or `OSError`) is never retried; `message` is ready to show.
- The process is registered with `ProcessRegistry` before `on_spawn` runs and unregistered when it exits, so `on_spawn` is where callers store the `Popen` and clear their "pending" flag.
