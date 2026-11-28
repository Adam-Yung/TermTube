#!/usr/bin/env python3
"""A change that adds many net non-test source lines says why in the growth log, in the same change."""
import re
import sys

import config
import lib
import worktree

ENTRY = re.compile(r"^- \d{4}-\d{2}-\d{2} \+\d+: \S.*$", re.M)


def counted(repo, path):
    """Non-test source. A deleted file is judged by its name, so removals offset additions."""
    if config.is_test(path) or repo.outside(path):
        return False
    if (repo.root / path).is_file():
        return repo.language(path) is not None
    return config.suffix_language(path) is not None


def net_added(repo):
    return sum(delta for path, delta in worktree.line_deltas(repo.root).items() if counted(repo, path))


def new_entry(repo):
    log = repo.cfg["growth_log"]
    if not (repo.root / log).is_file():
        return False
    at_head = ""
    if lib.git(repo.root, "ls-tree", "--name-only", "HEAD", "--", log).strip():
        at_head = lib.git(repo.root, "show", f"HEAD:{log}")
    return bool(set(ENTRY.findall(repo.read(log))) - set(ENTRY.findall(at_head)))


def check(repo):
    added, limit = net_added(repo), repo.caps["growth_lines"]
    problems = []
    if added > limit and not new_entry(repo):
        problems.append(f"+{added} net source lines (limit {limit}): add `- YYYY-MM-DD +{added}: why` "
                        f"to {repo.cfg['growth_log']}")
    return lib.verdict(problems, f"growth ({added:+d} lines)")


def main(argv=None):
    args = lib.parser(__doc__).parse_args(argv)
    return lib.main_guard(lambda: check(config.open_repo(args)))


if __name__ == "__main__":
    sys.exit(main())
