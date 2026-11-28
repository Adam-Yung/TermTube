#!/usr/bin/env python3
"""A changed source file comes with a changed mirror, or a mirror that says it was re-read.

    check-mirror-fresh.py                    judges every source changed against HEAD (staged, unstaged, untracked)
    check-mirror-fresh.py --stamp SOURCE...  writes `Reviewed: <hash8>` into the mirror after you re-read it

Which sources need a mirror: `mirrors` in .framework.json (the list docgate.py also reads), else every non-test source.
That mirrors exist and have a source is docgate.py's check, not this one.
"""
import fnmatch
import json
import re
import sys

import config
import lib
import worktree

REVIEWED = re.compile(r"^Reviewed: ([0-9a-f]{8})[ \t]*$", re.M)
FRAMEWORK = ".framework.json"


def mirror_of(repo, path):
    return f"{repo.cfg['mirror_dir']}/{path}.md"


def framework_mirrors(repo):
    path = repo.root / FRAMEWORK
    return (json.loads(path.read_text()).get("mirrors") or {}) if path.is_file() else {}


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def mirrored(repo, paths):
    spec = framework_mirrors(repo)
    present = [p for p in sorted(paths) if (repo.root / p).is_file()]
    if spec.get("sources"):
        return [p for p in present if matches(p, spec["sources"]) and not matches(p, spec.get("exclude", []))]
    sources = set(repo.sources(tests=False))
    return [p for p in present if p in sources]


def hash8(repo, path):
    return lib.git(repo.root, "hash-object", "--", path).strip()[:8]


def problem(repo, source, changed):
    mirror = mirror_of(repo, source)
    if not (repo.root / mirror).is_file():
        return f"{source}: no mirror {mirror}"
    if mirror in changed or hash8(repo, source) in REVIEWED.findall(repo.read(mirror)):
        return None
    return f"{source}: changed but {mirror} is not; update it, or re-read it and run check-mirror-fresh.py --stamp {source}"


def check(repo):
    changed = worktree.changed(repo.root)
    found = [problem(repo, source, changed) for source in mirrored(repo, changed)]
    return lib.verdict([line for line in found if line], "mirror freshness")


def stamp(repo, source):
    mirror = repo.root / mirror_of(repo, source)
    if not (repo.root / source).is_file() or not mirror.is_file():
        raise lib.GateError(f"{source}: the source and its mirror {mirror_of(repo, source)} must both exist")
    text = REVIEWED.sub("", mirror.read_text()).rstrip("\n")
    mirror.write_text(f"{text}\n\nReviewed: {hash8(repo, source)}\n")
    print(f"stamped {mirror_of(repo, source)}")


def stamp_all(repo, sources):
    for source in sources:
        stamp(repo, source)
    return 0


def main(argv=None):
    made = lib.parser(__doc__)
    made.add_argument("--stamp", nargs="+", metavar="SOURCE")
    args = made.parse_args(argv)
    if args.stamp:
        return lib.main_guard(lambda: stamp_all(config.open_repo(args), args.stamp))
    return lib.main_guard(lambda: check(config.open_repo(args)))


if __name__ == "__main__":
    sys.exit(main())
