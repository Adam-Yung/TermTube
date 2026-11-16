Handoff plan with acceptance criteria (T1 to T8 done, T9 is yours): `plans/2026-11-15-handoff-PLAN.md`.

# Todo

Next work, in order. Present reality is in `status.md`.

1. Go through `plans/2026-11-15-key-conflicts-PLAN.md` (K2 to K14) and say keep, change or skip for each.
2. Real-terminal check outside tmux and on Linux and Windows terminals: thumbnails (Kitty, iTerm2), `d` download, `b`, `y`, `p` (`docs/features/keybindings.md`). The tmux pass is recorded in `status.md`.
3. `pip install -r requirements-dev.txt` in the venv so the gate uses `.venv/bin/ruff` (the gate currently uses the `ruff` on `PATH`).
4. Check `feeds.channel_latest` on a network where RSS works: it returns 15 entries without durations where InnerTube returned about 30 with them (`docs/decisions/feeds-and-paging.md`, 2026-11-15).
