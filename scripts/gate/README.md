# Gates copied into the repo

The de-slop ratchets and `docgate.py`, copied so the pipeline can run them. They are vendored: no mirrors, not judged by themselves, not
linted by `ruff.toml`. `run.sh` is this repo's entry point; baselines are in `baselines/`; `lint/` pins `jscpd`
(`npm ci --ignore-scripts --prefix scripts/gate/lint`). Tests: `python -m unittest discover -s scripts/gate/tests`.

Counts may only shrink. Never raise a baseline or add an exclusion to get a pass.
