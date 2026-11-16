# src/plat.py

All OS branching lives here: config/cache/log directories, mpv IPC endpoints, clipboard, subprocess flags, the child-process registry and startup orphan reaping. Other modules import from here instead of checking `sys.platform`.

## Invariants

- Paths: config is `~/.config/TermTube` (`$XDG_CONFIG_HOME`) or `%APPDATA%\TermTube`; cache is `~/.cache/termtube` or `%LOCALAPPDATA%\TermTube\cache`; logs go to `<tmp>/TermTube`. Tests monkeypatch `IS_WINDOWS` / `IS_MACOS` on this module, so helpers must read those globals at call time.
- IPC: three endpoints (`termtube-mpv`, `-audio`, `-video`). Unix sockets live in `$XDG_RUNTIME_DIR`, else `/tmp/termtube-<uid>/` created `0700`, so another local user cannot connect to the player. Windows uses named pipes (`\\.\pipe\...`), which need no cleanup; `cleanup_ipc` is a no-op there.
- `ProcessRegistry` is the only list of children that must die with the app. Everything spawned for playback registers; `kill_all` (SIGTERM, shared wait, SIGKILL) runs from `main._emergency_cleanup`. See [docs/decisions/concurrency.md](../../decisions/concurrency.md).
- `download_thumbnail` retries without certificate verification after an SSL error (corporate MITM proxies). Only acceptable because thumbnails are public CDN images; do not reuse it for anything that carries credentials.

## Platform quirks

- Windows subprocesses get `CREATE_NEW_PROCESS_GROUP` (and `CREATE_NO_WINDOW` when `headless`) so Ctrl+C in the TUI does not reach mpv.
- `clip.exe` expects UTF-16LE on stdin; `pbcopy` takes UTF-8; Linux tries `wl-copy`, `xclip`, `xsel` in that order.
- `reap_orphans` runs at app start. It deletes `termtube-mpv*.sock` files and SIGTERMs any process matching `pgrep -f "mpv.*termtube-mpv"` except itself. Not run on Windows (no `pgrep`).

## Known limits

- `get_popen_kwargs` is an alias of `get_subprocess_flags`, kept because screens import both names.
- `_INSTALL_HINTS["yt-dlp"]` still describes the retired standalone binary; yt-dlp is now a pip dependency. Only `mpv` hints are shown in practice.
