# Quality gates

## 2026-11-28 — ratchets copied into the repo; one full de-slop

`scripts/gate/` holds copies of the de-slop ratchets and `docgate.py`, so the pipeline can run them without anyone's home folder. They
replace `check-doc-mirrors.sh` and `check-doc-links.py`. The pipeline runs them on Linux only: they judge text, not platform behaviour,
and the analyzers (`shellcheck`, `jscpd` pinned in `scripts/gate/lint/`) are there. Not judged: `scripts/*.ps1`, `termtube.cmd`
(no analyzer) and `scripts/gate/` itself. Counts may only shrink; at adoption every structure, duplication and dead-code count reached zero.

The test suite refuses to resolve names outside this machine: a test that reached YouTube hid a crash locally and showed it only in the
pipeline.
