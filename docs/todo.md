# Todo

The planned work is built; present state is in [status.md](status.md). Remaining, in order:

1. **Branch protection** on `main` requiring the six pipeline jobs, so a red platform blocks a merge (owner, in GitHub settings).
2. **Windows by hand** (a few minutes): `termtube` in Windows Terminal for keys, colours and thumbnails, which CI cannot see.
3. **Choose a license.** The README once linked a LICENSE file that does not exist; the link was removed. Add a `LICENSE` file once the owner decides.
4. Minor: the workflow's actions run on a deprecated Node 20 runtime (GitHub warns); bump `actions/checkout` and `actions/setup-python` when newer majors exist.
5. Minor: `thumbnail_format` offers no real choice; either wire a forced renderer or drop the setting.
