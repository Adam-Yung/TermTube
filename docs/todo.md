Handoff plan with acceptance criteria (T1 to T8 done, T9 is yours): `plans/2026-11-15-handoff-PLAN.md`.

# Todo

Next work, in order. Present reality is in `status.md`.

1. Run `scripts/dev-setup.sh --recreate` once: it builds a clean `.venv` with `ruff` (needs PyPI). Then `scripts/dev-setup.sh --check` and `scripts/verify.sh` (`docs/guides/environments.md`).
2. Key conflicts still open: K3, K6, K11, K12 (`plans/2026-11-15-key-conflicts-PLAN.md`).
3. Real-terminal check outside tmux and on Linux and Windows terminals: thumbnails (Kitty, iTerm2), `d` download, `b`, `y`, `p` (`docs/features/keybindings.md`). The tmux pass is recorded in `status.md`.
4. Run `scripts/diagnose-rss.py` from a different ISP (a phone hotspot) once. If RSS works there, check `feeds.channel_latest`: RSS gives 15 entries without durations where InnerTube gives about 30 with them (`docs/decisions/feeds-and-paging.md`).
