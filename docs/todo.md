# Todo

Open work only. Present state: [status.md](status.md). Plans: [plans/](plans/).

1. **Local files tab**.
2. **Live checks by the owner**: [guides/morning-checklist.md](guides/morning-checklist.md) (signed-in browser, real terminal, Windows Terminal).
3. **mpv-window keys in a playlist video run**: check in a real video window (tested only against a headless mpv).
4. **Branch protection** on `main` requiring the six pipeline jobs (owner, GitHub settings).
5. **Actions versions**: bump `actions/checkout` and `actions/setup-python` when newer majors exist (Node 20 deprecation).
6. **mpv lookup**: `player.mpv_exe` falls back to `PATH` (and mpv.net on Windows), against the bundled-binaries rule in `AGENTS.md`; the owner decides which is right.
