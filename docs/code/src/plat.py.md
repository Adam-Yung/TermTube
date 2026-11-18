# src/plat.py

All OS branching lives here: config/cache/log directories, mpv IPC endpoints, clipboard, subprocess flags, the child-process registry and startup orphan reaping. Other modules import from here instead of checking `sys.platform`.

## Invariants

- `TERMTUBE_CACHE_DIR` overrides the cache directory on every platform. It exists so an end-to-end run (`scripts/e2e-local.py`) can use a private cache on Windows, where the cache and the bundled tools share `%LOCALAPPDATA%`. Config and IPC are isolated with `XDG_CONFIG_HOME` / `APPDATA` and `XDG_RUNTIME_DIR`.
- Paths: config is `~/.config/TermTube` (`$XDG_CONFIG_HOME`) or `%APPDATA%\TermTube`; cache is `~/.cache/termtube` or `%LOCALAPPDATA%\TermTube\cache`; logs go to `<tmp>/TermTube`. Tests monkeypatch `IS_WINDOWS` / `IS_MACOS` on this module, so helpers must read those globals at call time.
- `atomic_write(path, data)` is the one temp-file-plus-`os.replace` writer, used by history, playlists and the cache. The temp file is unique (`mkstemp`) and the result is mode 0600; the cache's wrapper swallows `OSError` because cache files are best effort. Cache files used to be 0644 with a fixed `.tmp` name.
- Managed tools: `get_deps_dir()` is `~/.local/termtube-deps` (`%LOCALAPPDATA%\termtube-deps`); `get_deps_bin()` is its `bin` subdirectory; `is_tool_installed(name)` checks only there, never `PATH`. `src/main.py` prepends that bin to `PATH` at startup; `src/bootstrap.py` installs into it.
- IPC: three endpoints (`termtube-mpv`, `-audio`, `-video`). Unix sockets live in `$XDG_RUNTIME_DIR`, else `/tmp/termtube-<uid>/` created `0700`, so another local user cannot connect to the player. `private_dir` is the one creator for such directories (IPC and the debug log dir): 0700, and it raises `PermissionError` for a symlink, a non-directory or a directory owned by another user, and tightens a loose directory of ours. `_ipc_path` therefore fails closed: no socket is bound in an untrusted directory. `player.py` computes `IPC_SOCKET` at import, so such a directory stops the app at start with that error. Windows uses named pipes (`\\.\pipe\...`), which need no cleanup; `cleanup_ipc` is a no-op there.
- `ProcessRegistry` is the only list of children that must die with the app. Everything spawned for playback registers; `kill_all` (SIGTERM, shared wait, SIGKILL) runs from `main._emergency_cleanup`. See [docs/decisions/concurrency.md](../../decisions/concurrency.md).
- `download_thumbnail` fetches only http(s) URLs, reads at most 2 MB, and gives up on a certificate error. Its verified context also trusts the macOS keychains (`_macos_keychain_pem`: public certificates read once through `/usr/bin/security`; empty elsewhere), because a Python with its own CA bundle (conda, python.org) does not know a company's TLS-inspection root, which fails every inspected image host (`i.ytimg.com` on a Palo Alto firewall). `VERIFY_X509_STRICT` is cleared in that case since inspection roots often lack the key identifiers Python 3.13 requires; the chain and host name are still checked. Tests stub the keychain read. With `insecure=True` (config `insecure_thumbnails`, default off) it retries once without verification, for corporate MITM proxies; acceptable only because thumbnails are public CDN images, never reuse it for anything that carries credentials. `ui.thumbnail.download` decodes the file before keeping it.

## Platform quirks

- Windows subprocesses get `CREATE_NEW_PROCESS_GROUP` (and `CREATE_NO_WINDOW` when `headless`) so Ctrl+C in the TUI does not reach mpv.
- `clip.exe` expects UTF-16LE on stdin; `pbcopy` takes UTF-8; Linux tries `wl-copy`, `xclip`, `xsel` in that order.
- `reap_orphans` runs at app start (and returns at once on Windows: it relies on `os.getuid`, Unix sockets and `pgrep`, none of which exist there). It deletes `termtube-mpv*.sock` files and SIGTERMs any process matching `pgrep -f "mpv.*termtube-mpv"` except itself. Not run on Windows (no `pgrep`).

## Known limits

- `get_popen_kwargs` is an alias of `get_subprocess_flags`, kept because screens import both names.
- `_INSTALL_HINTS["yt-dlp"]` is the same pip command on every OS (yt-dlp is a library in TermTube's venv). Only `mpv` hints are shown in practice.
