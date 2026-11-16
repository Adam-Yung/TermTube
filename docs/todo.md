# Todo

The planned work is built; present state is in [status.md](status.md). Remaining, in order:

1. **Branch protection** on `main` requiring the six pipeline jobs, so a red platform blocks a merge (owner, in GitHub settings).
2. **Windows by hand** (a few minutes): `termtube` in Windows Terminal for keys, colours and thumbnails, which CI cannot see.
3. Minor: the workflow's actions run on a deprecated Node 20 runtime (GitHub warns); bump `actions/checkout` and `actions/setup-python` when newer majors exist.
