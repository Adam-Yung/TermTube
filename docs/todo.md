Handoff plan with acceptance criteria (T1 to T8 done, T9 is yours): `plans/2026-11-15-handoff-PLAN.md`.

# Todo

Next work, in order. Present reality is in `status.md`.

1. Real-terminal check of the keymap, audio, video, channel page and search on macOS, Linux and Windows terminals (`docs/features/keybindings.md`). Nothing has run against a real terminal since the restructure.
2. `pip install -r requirements-dev.txt` in the venv so the gate uses `.venv/bin/ruff` (the gate currently uses the `ruff` on `PATH`).
3. Delete `auto/cookies.txt` if you do not need it.
4. Check `feeds.channel_latest` on a network where RSS works: it returns 15 entries without durations where InnerTube returned about 30 with them (`docs/decisions/feeds-and-paging.md`, 2026-11-15).
