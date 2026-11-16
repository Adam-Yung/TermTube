Handoff plan (T1 to T8 done): `plans/2026-11-15-handoff-PLAN.md`. Present reality: `status.md`.

# Todo

Everything that was planned is built and verified on macOS (real terminal) and Linux (test suite). What is left needs a Windows machine or a decision.

1. **Windows, one real run** (`docs/history/2026-11-16-windows-audit.md`, open points 3 and 4): `.\scripts\setup.ps1 -NoPrompt`, then `termtube`; search, play audio (pause, seek, replace, stop over the named pipe), watch a video, quit.
2. **CI matrix:** add `macos-latest` and `windows-latest` to `.github/workflows/test.yml` (audit open point 1). Needs a trial run on GitHub; `verify.sh` is bash and `.venv\Scripts` differs from `.venv/bin`.
3. **Linux real session** (optional): install mpv, tmux and the bundled tools on the Linux machine and repeat the tmux pass. Needs package downloads there.
