#!/usr/bin/env python3
"""Plans and spikes expire: few handoffs and dated plan files; a spike says why it is kept."""
import re
import sys

import config
import lib

DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")
KEPT = re.compile(r"Kept because:")


def name(path):
    return path.rsplit("/", 1)[-1]


def plan_problems(repo):
    folder = repo.cfg["plans_dir"].rstrip("/")
    plans = [p for p in repo.files() if p.startswith(folder + "/")]
    handoffs = [p for p in plans if "HANDOFF" in name(p).upper()]
    dated = [p for p in plans if p not in handoffs and "HLD" not in name(p) and DATED.match(name(p))]
    problems = []
    for found, cap, label in ((handoffs, "handoffs", "handoff"), (dated, "dated_plans", "dated plan")):
        if len(found) > repo.caps[cap]:
            problems.append(f"{folder}: {len(found)} {label} files, at most {repo.caps[cap]}: {', '.join(found)}")
    return problems


def kept(repo, readme):
    return (repo.root / readme).is_file() and bool(KEPT.search(repo.read(readme)))


def spike_problems(repo):
    folder = repo.cfg["spikes_dir"].rstrip("/") + "/"
    spikes = sorted({p[len(folder):].split("/")[0] for p in repo.files()
                     if p.startswith(folder) and "/" in p[len(folder):]})
    return [f"{folder}{spike}: needs a README.md with a `Kept because:` line"
            for spike in spikes if not kept(repo, f"{folder}{spike}/README.md")]


def check(repo):
    return lib.verdict(plan_problems(repo) + spike_problems(repo), "expiry")


def main(argv=None):
    args = lib.parser(__doc__).parse_args(argv)
    return lib.main_guard(lambda: check(config.open_repo(args)))


if __name__ == "__main__":
    sys.exit(main())
