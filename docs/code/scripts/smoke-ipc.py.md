# scripts/smoke-ipc.py

The one check mocks cannot give: a real mpv driven through `src.player`, the code the audio controller uses. Run it on a new platform or after touching `player.py`, `plat.py` IPC paths or `requirements.txt`'s `pywin32` line. Context: `docs/guides/ci.md`. Replacing a playing track is covered only by mocked tests, here and in the end-to-end run. `scripts/e2e-local.py` goes one level up: the same IPC, but driven by the real app and real keys.

- Needs no audio device, file or network: mpv starts with `--no-config --ao=null` on a generated tone (`av://lavfi:sine=...`, 30 s). `--no-config` keeps the user's `mpv.conf` out of the result.
- Eight steps, each printed `PASS` or `FAIL`: connect and poll, duration, position advances, pause reported and position held, resume, absolute seek, relative seek, `quit` ends mpv (exit code 0 or 4). On Windows this is the named pipe through pywin32 (`\\.\pipe\termtube-smoke-<pid>`); elsewhere a Unix socket. The pipe or socket name carries the process id so it cannot touch a running TermTube.
- Exit codes: 0 all passed (or mpv missing without `--require-mpv`); 1 a step failed (mpv's stderr is printed); 2 mpv missing with `--require-mpv`. mpv is found with `player.mpv_exe(headless=True)`, so the bundled copy in `termtube-deps` wins.
- It reaches into `src.plat._ipc_path` on purpose, as `bench-sources.py` does with innertube.
- Cleanup runs in `finally`: terminate, close the pooled socket, remove the socket file and the temp `input.conf`.
- Test: `src/tests/integration/test_smoke_ipc.py` runs it when mpv exists (about 3 s), so every gate run on a machine with mpv covers the real IPC.
