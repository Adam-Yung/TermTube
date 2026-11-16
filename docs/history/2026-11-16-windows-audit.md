# Windows dry audit, 2026-11-16

Static review only. No Windows machine and no PowerShell were available, so nothing here was executed on Windows. Method: read every Windows
branch (`plat.py`, `player.py`, `bootstrap.py`, `main.py`), `termtube.cmd`, `setup.ps1` and `uninstall.ps1`; searched `src` for POSIX-only APIs
(`os.getuid`, `AF_UNIX`, `SIGHUP`, `fcntl`, `pgrep`, `/tmp`, `preexec_fn`, `shell=True`); searched the tests for POSIX assumptions; read the CI file.

## Found and fixed

| # | Finding | Effect on Windows | Fix |
|---|---|---|---|
| W1 | `plat.reap_orphans()` called `_unix_ipc_dir()` (uses `os.getuid`) before its `IS_WINDOWS` return | `AttributeError` on every start; hidden by a bare `except` in `TermTubeApp.on_mount` | Return first; test with a monkeypatched `IS_WINDOWS` that fails if `os.getuid` or `pgrep` is touched |
| W2 | `run_mpv_with_retries` captured stderr in text mode with the locale codec | Without UTF-8 mode (cp1252), mpv output containing `ā` (byte `0x81`) made `communicate()` raise and left `returncode` unset, so a good run looked like a failure. `termtube.cmd` sets `PYTHONUTF8=1`, which hides it; `python src/main.py` does not | `encoding="utf-8", errors="replace"`; a real-subprocess test feeds invalid bytes |
| W3 | `history.add()` ran on the UI thread and let `OSError` out of `os.replace` | A history file held open by antivirus or an indexer would crash the app. Same on any OS with a full disk | Write failures are logged and dropped |
| W4 | `scripts/setup.ps1` working copy had lost its CRLF endings (my earlier edit) | None in git (blobs are LF, `.gitattributes` converts on checkout); a direct copy of the tree would carry LF | Restored CRLF, kept the BOM |

## Checked and fine

- `signal.SIGHUP` is guarded (`main.py`). `AF_UNIX` is only on the non-Windows path (`player._get_persistent_socket`). `cleanup_ipc` returns on Windows.
- IPC: named pipes `\\.\pipe\termtube-mpv-*` through `pywin32`; the audio controller's per-session suffix works for them (`_socket_for` appends to a name without extension). `requirements.txt` pulls `pywin32` only on `win32`.
- `get_subprocess_flags` adds `CREATE_NEW_PROCESS_GROUP` and `CREATE_NO_WINDOW`; `terminate_process` uses `terminate()` then `kill()`.
- `termtube.cmd` finds `.venv\Scripts\python.exe`, falls back to `%LOCALAPPDATA%\Programs\TermTube`, sets `PYTHONUTF8` and `PYTHONIOENCODING`, and routes `--uninstall` to `uninstall.ps1`.
- `setup.ps1` already preserves the previous `.venv` across reinstalls (stash and restore) and skips pip when `requirements.txt` is unchanged, so it needs no `--refresh` like `setup.sh`. Its help text no longer lists removed flags.
- New code of this session: `atomic_write` (temp file in the target directory, `os.replace`), `escape_markup`, the keep-alive `http.client` transport (Windows uses the system certificate store through `ssl`), `AudioController` and the hints use no POSIX-only calls. `get_deps_bin` reads `LOCALAPPDATA`.
- Tests: the Unix-socket tests are skipped on Windows, the two bash-script test files are skipped without bash, and `test_platform` monkeypatches `IS_WINDOWS` for the path tests.

## Open (not fixed)

1. **CI ran only `ubuntu-latest`, Python 3.12** (since addressed: the workflow now has macOS and Windows jobs and a real-installer job, `docs/guides/ci.md`; results pending their first run). Nothing exercises Windows or macOS automatically. A `windows-latest` and `macos-latest` matrix would catch most of the above. `verify.sh` is bash; the Windows runner has Git Bash (`shell: bash`), and the script falls back to `python3`, which the Windows runner may lack: needs a try. Not changed because it cannot be tested here.
2. **Dev tooling is bash only:** `verify.sh`, `dev-setup.sh`, `check-doc-mirrors.sh`, `setup.sh --refresh`. A Windows contributor needs Git Bash or WSL; `verify.sh` looks for `.venv/bin/python`, while a Windows venv has `.venv\Scripts\python.exe`.
3. **PowerShell scripts were not parsed.** `setup.ps1`, `uninstall.ps1` and the launcher logic need one run on Windows (`.\scripts\setup.ps1 -NoPrompt`, then `termtube`). Under `Set-StrictMode -Version Latest` an undefined variable in an untested branch only fails at run time.
4. **The named-pipe path was untested end to end** (unit tests mock `win32file`). `scripts/smoke-ipc.py` now drives a real mpv through it (poll, pause, resume, seek, quit); it passes on macOS and runs on Windows in the `windows-install` CI job. The audio controller's track replacement over the pipe is still covered only by its mocked tests.
5. `playlist.py` writes (`add_video`) can still raise `OSError` into a UI action; the same lock-contention risk as W3, lower frequency.
6. `docs/guides/environments.md` describes the Unix layout only. The Windows layout is `%LOCALAPPDATA%\Programs\TermTube` (app and venv) and `%LOCALAPPDATA%\termtube-deps\bin`.
