#!/usr/bin/env python3
"""The status and todo docs stay small: hard caps, no baseline. Move history out, do not raise the cap."""
import sys

import config
import lib


def check(repo):
    problems = []
    for path, cap in repo.cfg["doc_bytes"].items():
        full = repo.root / path
        size = full.stat().st_size if full.exists() else 0
        if size > cap:
            problems.append(f"{path}: {size} bytes, over the {cap} byte cap")
    return lib.verdict(problems, "doc size")


def main(argv=None):
    args = lib.parser(__doc__).parse_args(argv)
    return lib.main_guard(lambda: check(config.open_repo(args)))


if __name__ == "__main__":
    sys.exit(main())
