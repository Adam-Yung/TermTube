# src/player.py

Launch helpers for mpv and the commands used to control it. It owns the mpv executable lookup, the temporary `input.conf`, the
headless audio command line, and the two IPC transports. It owns the launch loop (`run_mpv_with_retries`) but not what a result means: screens spawn through it and map the outcome (`src/tui/audio_controller.py`, `src/tui/screens/watch_modal.py`).

Decisions: `docs/decisions/playback.md`, `docs/decisions/concurrency.md`.

## IPC

`send_ipc_command`, `poll_audio_properties` and `close_persistent_socket` are the API the screens use; the transport is `src/mpv_ipc.py`.
`close_all_sockets()` runs at app exit (`src/main.py`): it closes the pooled sockets and deletes the temp input confs.

## Executable lookup (`mpv_exe`)

Order: the bundled mpv in `~/.local/termtube-deps/bin/`, then `PATH`, then (Windows only) mpv.net.

With `headless=True` on Windows only the TermTube-bundled `mpv.exe` or a `PATH` `mpv.exe` without an `mpvnet.exe` sibling qualifies. The
function returns `None` otherwise. Symptom of ignoring this: a visible mpv window pops up on every audio play, because mpv.net ignores
`--force-window=no`, and its install dir ships an `mpv.exe` stub that redirects to `mpvnet.exe`. See the 2026-05-16 entry in the playback
log.

## Input config

`write_input_conf` writes a temp `input.conf` (digits seek to percent, `h`/`l`/`H`/`L` and arrows seek, `q` quits) for the video player,
where mpv owns the keyboard. These are mpv's keys, separate from the TUI keymap in `src/tui/keymap.py`. Files are tracked in
`_temp_input_confs` and removed by `close_all_sockets`. `sequence=True` rebinds `>`, `<`, `q`, `CLOSE_WIN` and `Meta+q` to `quit 10/11/12`, so a playlist run can tell the end of a video (exit 0) from a step or a close. `tests/integration/test_mpv_sequence_keys.py` checks the codes against a real mpv.

## Audio command

`audio_command` builds the headless command. With a pre-resolved `stream_url` it passes `--no-ytdl` and plays the URL directly. Without
one, mpv resolves `page_url` through its own yt-dlp hook, with `--ytdl-format` and cookie flags converted by `cookie_args_to_ytdl_raw`
(only `--key value` pairs convert; bare flags are dropped). `--msg-level=all=error` keeps stderr small enough to capture and summarise via
`friendly_mpv_error`, which maps known error text to a toast and truncates unknown text to 100 characters.

## Known limits

- `send_ipc_command` returns the first parsed line, which can be an event rather than the reply if mpv emitted one just before.

## Launch loop

`run_mpv_with_retries(build_cmd, ...)` is the only place mpv is spawned and retried; the audio controller (`headless=True`, stderr captured) and `WatchModal` (`headless=False`, stderr discarded) share it and keep their own command builders. It returns an `MpvOutcome` instead of acting on it:

- `ok` (exit 0, 4, or a run code 10, 11, 12) and `killed` (exit 3, the stop key or a signal) are normal exits; the caller decides what each means (audio advances the queue on `ok` and says nothing on `killed`; video dismisses on both).
- Any other exit retries after 1 s, up to `MPV_MAX_ATTEMPTS` (3), then `failed` with the last exit code and stderr. `build_cmd(attempt)` is where a caller re-resolves an expired stream URL for attempts after the first.
- mpv's stdin is `DEVNULL` and the audio command uses `--no-input-terminal`, not `--no-terminal`: mpv must not read the TUI's keystrokes, but its error messages (`--msg-level=all=error`) must reach the captured stderr. With `--no-terminal` a Windows failure read "exit code 2, no stderr output" and the cause was invisible.
- Captured stderr is decoded as UTF-8 with `errors="replace"`, never the locale codec: on Windows without UTF-8 mode (cp1252) a title containing `ā` made `communicate()` raise and left `returncode` unset.
- `stale` is returned when `is_stale()` is true before a launch or after an exit; the process may have run, and the caller discards the result.
- `launch_error` (mpv missing, or `OSError`) is never retried; `message` is ready to show.
- The process is registered with `ProcessRegistry` before `on_spawn` runs and unregistered when it exits, so `on_spawn` is where callers store the `Popen` and clear their "pending" flag.

`start_args(start)` is the one place the `--start=<s>` flag is built (resume position); `audio_command(start=)` and `WatchModal._build_command` both use it. It goes before the `--` that separates options from the URL.

- `source_args`: a file on disk gets `--access-references=no` (audio and video). mpv otherwise follows references inside a local file: a "song.mp3" holding `#EXTM3U` and a URL made it fetch that URL. Stream URLs (`http`, `https`) are unchanged.
