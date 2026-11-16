Handoff plan (T1 to T8 done): `plans/2026-11-15-handoff-PLAN.md`. Present reality: `status.md`.

# Todo

Everything that was planned is built and verified on macOS (real terminal) and Linux (test suite). What is left needs a Windows machine or a decision.

1. **Windows through CI:** push a branch, watch the three jobs (`docs/guides/ci.md`), fix what fails. The jobs are written and the smoke script passes on macOS; the Windows jobs have not run yet.
2. **Windows by hand** (a few minutes, after CI is green): `termtube` on Windows Terminal for keys, colours and thumbnails, which CI cannot see.
3. **Linux real session** (optional): install mpv, tmux and the bundled tools on the Linux machine and repeat the tmux pass. Needs package downloads there.
