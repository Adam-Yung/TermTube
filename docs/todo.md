Handoff plan (T1 to T8 done): `plans/2026-11-15-handoff-PLAN.md`. Present reality: `status.md`.

# Todo

The planned work is built. The pipeline (`docs/guides/ci.md`) is on `main` and green on Linux, macOS and Windows; the canary has run once (6 of 6 checks passed).

1. **Consider branch protection** on `main` requiring the six pipeline jobs, so a red platform blocks a merge.
2. **Windows by hand** (a few minutes): `termtube` on Windows Terminal for keys, colours and thumbnails, which CI cannot see.
3. Minor: the workflow's actions run on a deprecated Node 20 runtime (GitHub warns); bump `actions/checkout` and `actions/setup-python` when newer majors exist.
