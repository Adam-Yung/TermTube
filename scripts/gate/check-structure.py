#!/usr/bin/env python3
"""Structure ratchet: nesting, complexity, length, comment blocks, suppressions and shell warnings may only go down.

    check-structure.py            fails when a file's count rose, or fell below the baseline
    check-structure.py --update   lowers the baseline (never raises it)
    check-structure.py --rebuild  after files moved or split; refused if a rule's total grew
    check-structure.py --init     creates the baseline; refuses to overwrite one
    check-structure.py --report   prints the counts (the baseline measurement)
"""
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import config
import lib
import ratchet
import struct_js
import struct_limits
import struct_python
import struct_rust
import struct_shell
import struct_swift

RULES = (struct_swift, struct_python, struct_js, struct_rust, struct_shell, struct_limits)
BASELINE = "structure.json"


def refuse_unanalyzed(repo):
    """A language with no analyzer here is a hole in the gate until the owner accepts it by name."""
    present = Counter(repo.language(p) for p in repo.sources())
    holes = [f"{lang} ({count} files)" for lang, count in sorted(present.items())
             if lang not in config.ANALYZED and lang not in repo.cfg["unanalyzed_ok"]]
    if holes:
        raise lib.GateError(f"no complexity analyzer for {', '.join(holes)}: add the language to unanalyzed_ok "
                            "in .deslop.json (owner's call) and lint it another way")


def check(args):
    repo = config.open_repo(args)
    refuse_unanalyzed(repo)
    with ThreadPoolExecutor(len(RULES)) as pool:
        results = list(pool.map(lambda rule: rule.violations(repo), RULES))
    found = sorted((v for result in results for v in result), key=lambda v: (v.path, v.line, v.rule))
    return ratchet.apply("structure", repo.root / repo.cfg["baseline_dir"] / BASELINE, found, args.mode)


def main(argv=None):
    made = lib.parser(__doc__)
    ratchet.add_modes(made)
    args = made.parse_args(argv)
    return lib.main_guard(lambda: check(args))


if __name__ == "__main__":
    sys.exit(main())
