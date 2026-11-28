"""Per rule, per file violation counts against a committed baseline that may only go down."""
import json
from collections import defaultdict

import lib


def tally(violations):
    counts = defaultdict(lambda: defaultdict(int))
    for item in violations:
        counts[item.rule][item.path] += 1
    return {rule: dict(files) for rule, files in counts.items()}


def keys(first, second):
    for rule in sorted(set(first) | set(second)):
        for path in sorted(set(first.get(rule, {})) | set(second.get(rule, {}))):
            yield rule, path


def load(path):
    if not path.exists():
        raise lib.GateError(f"baseline {path.name} is missing: create it once with --init")
    return json.loads(path.read_text())


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def save(path, counts):
    write_json(path, {rule: dict(files) for rule, files in counts.items() if files})


def lowered(baseline, counts):
    out = defaultdict(dict)
    for rule, path in keys(baseline, counts):
        value = min(baseline.get(rule, {}).get(path, 0), counts.get(rule, {}).get(path, 0))
        if value:
            out[rule][path] = value
    return out


def compare(baseline, violations):
    """(rises, falls): report lines for counts above the baseline, and for counts below it."""
    counts = tally(violations)
    rises, falls = [], []
    for rule, path in keys(baseline, counts):
        was = baseline.get(rule, {}).get(path, 0)
        now = counts.get(rule, {}).get(path, 0)
        if now > was:
            rises.append(f"{rule}: {path}: {now} (baseline {was})")
            rises.extend(f"  {v.path}:{v.line}: {v.message}" for v in violations if (v.rule, v.path) == (rule, path))
        if now < was:
            falls.append(f"{rule}: {path}: {now} (baseline {was}), run --update")
    return rises, falls


def totals(violations):
    counts = tally(violations)
    lines = [f"  {rule}: {sum(files.values())} in {len(files)} file(s)" for rule, files in sorted(counts.items())]
    return "\n".join(lines) or "  none"


def grown_totals(baseline, counts):
    grown = []
    for rule, files in sorted(counts.items()):
        was, now = sum(baseline.get(rule, {}).values()), sum(files.values())
        if now > was:
            grown.append(f"{rule}: total {now} (baseline {was})")
    return grown


def init(name, path, violations):
    if path.exists():
        raise lib.GateError(f"baseline {path.name} exists: --init never overwrites one")
    save(path, tally(violations))
    print(f"{name}: baseline written to {path.name}\n{totals(violations)}")
    return 0


def rebuild(name, path, violations):
    """After files moved or split: new per-file counts, only if no rule's total grew."""
    counts = tally(violations)
    grown = grown_totals(load(path), counts)
    if not grown:
        save(path, counts)
    return lib.verdict(grown, f"{name} (baseline rebuilt)")


def apply(name, path, violations, mode):
    """mode is None (check), "init", "update", "rebuild" or "report"."""
    if mode == "report":
        print(f"{name}:\n{totals(violations)}")
        return 0
    if mode == "init":
        return init(name, path, violations)
    if mode == "rebuild":
        return rebuild(name, path, violations)
    baseline = load(path)
    rises, falls = compare(baseline, violations)
    if mode == "update":
        save(path, lowered(baseline, tally(violations)))
        return lib.verdict(rises, f"{name} (baseline lowered)")
    return lib.verdict(rises + falls, name)


def add_modes(made):
    group = made.add_mutually_exclusive_group()
    group.add_argument("--init", dest="mode", action="store_const", const="init", help="create the baseline")
    group.add_argument("--update", dest="mode", action="store_const", const="update", help="lower the baseline")
    group.add_argument("--rebuild", dest="mode", action="store_const", const="rebuild",
                       help="after moves or splits; refused if a total grew")
    group.add_argument("--report", dest="mode", action="store_const", const="report", help="print counts only")
