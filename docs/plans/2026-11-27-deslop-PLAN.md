# De-slop, 2026-11-27

Remove slop without changing behaviour. Gates first, then cleanup.

## Owner answers
Full restructure, merge duplicates, delete proven dead code. Delete stale docs. Brief and objectives approved. Installs permitted. All gates.
Gate scripts copied into the repo. Merge and push at the end. Everything may be run live (`AGENTS.md` download and rate-limit rules still hold).

## Baseline
comment-block 3, file-lines 15, C901 18, PLR0912 9, PLR1702 48, nested-def 184, shellcheck 4, suppression 55; clones 0; dead code 0.
Not judged: `scripts/*.ps1`, `termtube.cmd` (no analyzer), `scripts/gate/` (vendored).

## Steps
1. Gates and baselines.
2. Docs: delete finished plans and history, keeping true facts in their owner pages.
3. Refactor by area, one Sonnet agent each, patches applied here: `src` core, `src/tui`, `src/tests` and `scripts`.
4. Mirrors, feature pages (`> Verified`, `> Serves`, `> Owns`), then the `features` and `freshness` checks go on.
5. Defects found on the way: failing test first.
6. Full gate, live checks, review (Sonnet: `AGENTS.md` forbids Opus), merge, push, watch the pipeline.

## Deleted docs
| Removed | Why | Still-true facts now in |
|---|---|---|
| `history/2026-11-16-status-log.md` | Past status log | Nothing new: already in `status.md`, feature pages, guides and decisions |
| `history/2026-11-16-windows-audit.md` | Findings fixed or documented | Track replacement tested only with mocks: `code/scripts/smoke-ipc.py.md` |
| `plans/2026-11-15-handoff-PLAN.md` | Tasks done or dropped | Nothing new |
| `plans/2026-11-15-key-conflicts-PLAN.md` | All items decided | Nothing new: `features/keybindings.md` and code mirrors |
| `plans/2026-11-15-optimization-PLAN.md` | Built or dropped | Source ladder and adoption rule: `features/sources.md` |
| `plans/2026-11-17-ux-and-performance-audit-PLAN.md` | Audit work built; unbuilt ideas dropped | Subscriptions stays a channel list: `features/sources.md` |
| `plans/2026-11-18-channel-page-HANDOFF.md` | P7.1 and P7.2 done | Nothing new |
