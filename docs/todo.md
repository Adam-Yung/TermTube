Handoff plan (T1 to T8 done): `plans/2026-11-15-handoff-PLAN.md`. Present reality: `status.md`.

# Todo

The planned work is built. The pipeline (`docs/guides/ci.md`) is green on Linux, macOS and Windows on branch `ci/platform-pipeline`.

1. **Merge the branch.** Decide how: fast-forward `main` to it, or a pull request. Until then `main` on GitHub still has the old one-job workflow, and the 17 local commits are unpushed.
2. **Run `canary.yml` once** after the merge (`gh workflow run canary.yml`); it cannot be dispatched from a branch.
3. **Consider branch protection** on `main` requiring the six pipeline jobs, so a red platform blocks a merge.
4. **Windows by hand** (a few minutes): `termtube` on Windows Terminal for keys, colours and thumbnails, which CI cannot see.
5. Minor: the workflow's actions run on a deprecated Node 20 runtime (GitHub warns); bump `actions/checkout` and `actions/setup-python` when newer majors exist.
