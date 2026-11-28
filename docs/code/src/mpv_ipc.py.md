# src/mpv_ipc.py

The transport under `src/player.py`'s IPC commands: pooled Unix sockets, Windows named pipes, and the batched property poll.
Split from `player.py`. Decisions: `docs/decisions/playback.md`, `docs/decisions/concurrency.md`.

## IPC transports

| | Unix (macOS, Linux) | Windows |
|---|---|---|
| Endpoint | Unix socket in a 0700 per-user dir (`plat._ipc_path`) | named pipe `\\.\pipe\termtube-mpv...` |
| Connection | persistent, pooled per path in `_persistent_sockets` | connect-per-call (`CreateFile`, then close) |
| Client | stdlib `socket` | `pywin32` (`win32file`, `win32pipe`), imported lazily |
| Missing client or endpoint | `None` socket, empty reply | `ImportError` or `pywintypes.error`, empty reply |

`IS_WINDOWS` selects the transport inside `send_recv` and `poll`. Callers never branch on it. Every failure ends as an
empty reply, `None`, or `(None, None, False)`: a dead mpv is a normal state, not an exception.

Windows pipes are not pooled: each call opens and closes the handle, and `WaitNamedPipe` covers `ERROR_PIPE_BUSY` while mpv serves another
client.

## Threading rules for the socket pool

IPC runs from worker threads (`audio_poll` group polls every 0.5 s, seek and pause commands come from the UI thread) and the same mpv
socket is shared by all of them.

- `_persistent_lock` guards the `_persistent_sockets` dict only. It is never held across `send` or `recv`.
- `_get_ipc_lock(path)` returns one lock per socket path. Every send/recv exchange on that path runs under it. Without it, two threads
  interleave their writes on the single stream and read each other's replies.
- Lock order is per-path lock, then `_persistent_lock` (inside `_get_persistent_socket` and `drop_socket`). Nothing takes them
  in the reverse order.
- A broken pipe, reset or EOF drops the pooled socket and retries once with a fresh connection. A second failure returns empty. A
  `socket.timeout` is not an error: the reply read stops and returns what arrived.
- `drop_socket` also removes the path lock. A thread already holding the old lock keeps using that object, so a new thread may
  briefly hold a different lock for the same path. This is safe only because the dropped socket is closed, and the next exchange
  reconnects.
- `_ipc_locks` is bounded by `_IPC_LOCKS_MAX` and cleared when full. Audio sessions use a new socket path per session
  (`-2`, `-3` suffixes), so paths accumulate.
- `player.close_persistent_socket(path)` must be called when a track ends or mpv exits. Otherwise the next session on the same path would
  reuse a socket that points at a dead mpv.

## Batched polling

`poll` asks for `time-pos`, `duration` and `pause` in one round trip, tagged with `request_id` 0 to 2. mpv also emits
unsolicited event lines on the same socket, so replies are matched by `request_id`, never by order. Unix reads until all three arrive or the
1 s socket timeout hits. Missing values come back as `None` (`paused` is `False`). Without `pywin32` the Windows path returns nothing.

## Known limits

- Tests cover the Windows pipe path against fake `pywin32` modules (`src/tests/unit/test_mpv_pipe.py`) and the Unix path in `src/tests/integration/test_mpv_ipc.py`. The Windows CI job also drives a real mpv over the pipe with `scripts/smoke-ipc.py`.
- The reply read on Unix returns once a newline arrives, so one extra queued event line can be left in the stream. Request-id matching makes the polling path immune.
