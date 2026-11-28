#!/usr/bin/env python3
"""Copy-paste ratchet: the number of clones and of duplicated lines may only shrink (jscpd).

    check-duplication.py            fails when either number rose, or fell below the baseline
    check-duplication.py --update   lowers the baseline (never raises it)
    check-duplication.py --rebuild  after files moved; refused if either number grew
    check-duplication.py --init     creates the baseline; refuses to overwrite one
    check-duplication.py --report   prints the numbers
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

import config
import lib
import ratchet

BASELINE = "duplication.json"
MEASURES = ("clones", "duplicated_lines")


def scan(repo):
    files = repo.product_files()
    if not files:
        return []
    with tempfile.TemporaryDirectory(prefix="deslop-jscpd.") as out:
        settings = Path(out, "settings.json")
        settings.write_text(json.dumps(
            {"minTokens": repo.caps["clone_tokens"], "maxLines": 100000, "maxSize": "10mb"}))
        cmd = [repo.node_tool("jscpd"), "--config", str(settings),
               "--reporters", "json", "--output", out, "--silent", "--no-tips", "--absolute"]
        lib.run(cmd + files, repo.root, timeout=600)
        report = Path(out, "jscpd-report.json")
        if not report.exists():
            raise lib.GateError("jscpd wrote no report")
        return json.loads(report.read_text())["duplicates"]


def side(repo, part):
    return lib.relative(repo.root, part["name"]), part["start"], part["end"]


def clones(repo):
    """(pair key, line count, printable text) of every clone."""
    found = []
    for clone in scan(repo):
        first, second = sorted((side(repo, clone["firstFile"]), side(repo, clone["secondFile"])))
        text = f"  {first[0]}:{first[1]}-{first[2]} = {second[0]}:{second[1]}-{second[2]}"
        found.append((f"{first[0]}|{second[0]}", clone["lines"], text))
    return sorted(found)


def measure(found):
    pairs = Counter(key for key, _, _ in found)
    return {"clones": len(found), "duplicated_lines": sum(n for _, n, _ in found), "pairs": dict(sorted(pairs.items()))}


def grown(baseline, now, found):
    new = {key for key, count in now["pairs"].items() if count > baseline["pairs"].get(key, 0)}
    return [text for key, _, text in found if key in new] or [text for _, _, text in found]


def rises(baseline, now, found):
    out = [f"{m}: {now[m]} (baseline {baseline[m]})" for m in MEASURES if now[m] > baseline[m]]
    return out + grown(baseline, now, found) if out else out


def falls(baseline, now):
    return [f"{m}: {now[m]} (baseline {baseline[m]}), run --update" for m in MEASURES if now[m] < baseline[m]]


def lower(baseline, now):
    out = {m: min(baseline[m], now[m]) for m in MEASURES}
    out["pairs"] = {k: min(v, now["pairs"][k]) for k, v in baseline["pairs"].items() if k in now["pairs"]}
    return out


def init(path, now):
    if path.exists():
        raise lib.GateError(f"baseline {path.name} exists: --init never overwrites one")
    ratchet.write_json(path, now)
    print(f"duplication: baseline {now['clones']} clones, {now['duplicated_lines']} duplicated lines")
    return 0


def judge(path, now, found, mode):
    baseline = ratchet.load(path)
    up = rises(baseline, now, found)
    if mode == "update":
        ratchet.write_json(path, lower(baseline, now))
        return lib.verdict(up, "duplication (baseline lowered)")
    if mode == "rebuild":
        if not up:
            ratchet.write_json(path, now)
        return lib.verdict(up, "duplication (baseline rebuilt)")
    return lib.verdict(up + falls(baseline, now), "duplication")


def check(args):
    repo = config.open_repo(args)
    path = repo.root / repo.cfg["baseline_dir"] / BASELINE
    found = clones(repo)
    now = measure(found)
    if args.mode == "report":
        print(f"duplication:\n  clones: {now['clones']}\n  duplicated lines: {now['duplicated_lines']}")
        return 0
    return init(path, now) if args.mode == "init" else judge(path, now, found, args.mode)


def main(argv=None):
    made = lib.parser(__doc__)
    ratchet.add_modes(made)
    args = made.parse_args(argv)
    return lib.main_guard(lambda: check(args))


if __name__ == "__main__":
    sys.exit(main())
