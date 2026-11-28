#!/usr/bin/env python3
"""Dead code ratchet: unused Python, JS/TS and Swift declarations and unreferenced scripts may only shrink.

    check-deadcode.py            fails when a file's count rose, or fell below the baseline
    check-deadcode.py --update   lowers the baseline (never raises it)
    check-deadcode.py --rebuild  after files moved or split; refused if a rule's total grew
    check-deadcode.py --init     creates the baseline; refuses to overwrite one
    check-deadcode.py --report   prints the counts
    check-deadcode.py --list     prints every hit

Name-based: a hit is a question, not proof. Search for reflection, string dispatch and external callers before deleting.
"""
import sys

import config
import dead_funcs
import dead_scripts
import dead_swift
import lib
import ratchet

RULES = (dead_swift, dead_funcs, dead_scripts)
BASELINE = "deadcode.json"


def hits(repo):
    found = [item for rule in RULES for item in rule.violations(repo)]
    return sorted(found, key=lambda v: (v.rule, v.path, v.line))


def check(args):
    repo = config.open_repo(args)
    found = hits(repo)
    if args.list:
        print("\n".join(f"{v.rule}: {v.path}:{v.line}: {v.message}" for v in found))
        return 0
    return ratchet.apply("dead code", repo.root / repo.cfg["baseline_dir"] / BASELINE, found, args.mode)


def main(argv=None):
    made = lib.parser(__doc__)
    ratchet.add_modes(made)
    made.add_argument("--list", action="store_true")
    args = made.parse_args(argv)
    return lib.main_guard(lambda: check(args))


if __name__ == "__main__":
    sys.exit(main())
