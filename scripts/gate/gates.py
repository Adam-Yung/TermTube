#!/usr/bin/env python3
"""Runs the gates listed under `gates` in .deslop.json.

    gates.py            check; the exit status is the worst of the gates (0 clean, 1 findings, 2 could not run)
    gates.py --report   measure: structure, duplication and dead code counts, and unowned files; writes nothing
    gates.py --init     create the baselines of the ratchets
    gates.py --update   lower them
    gates.py --rebuild  after files moved or split

Doc gates (brief, mirrors exist, links, freshness, map) are the framework's docgate.py: run both from verify.sh.
"""
import importlib
import sys

import config
import lib
import ratchet

RATCHETS = ("structure", "duplication", "deadcode")
KNOWN = RATCHETS + ("mirror-fresh", "features", "doc-size", "expiry", "growth")


def passthrough(args):
    out = ["--root", str(args.root)]
    return out + (["--config", str(args.config)] if args.config else [])


def selected(args):
    gates = config.open_repo(args).cfg["gates"]
    unknown = [g for g in gates if g not in KNOWN]
    if unknown:
        raise lib.GateError(f"unknown gate(s) in .deslop.json: {', '.join(unknown)}")
    if args.mode:
        return [g for g in gates if g in RATCHETS]
    return gates


def run_gate(name, args):
    extra = [f"--{args.mode}"] if args.mode else []
    return importlib.import_module(f"check-{name}").main(passthrough(args) + extra)


def run_all(args):
    worst = max([run_gate(name, args) for name in selected(args)], default=0)
    if args.mode == "report" and "features" in config.open_repo(args).cfg["gates"]:
        print("unowned source files:")
        importlib.import_module("check-features").main(passthrough(args) + ["--list-unowned"])
    return worst


def main(argv=None):
    made = lib.parser(__doc__)
    ratchet.add_modes(made)
    args = made.parse_args(argv)
    return lib.main_guard(lambda: run_all(args))


if __name__ == "__main__":
    sys.exit(main())
