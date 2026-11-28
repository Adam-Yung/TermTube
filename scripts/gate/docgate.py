#!/usr/bin/env python3
"""Doc gates shared by every repo on the framework (generalized from prisma-encryptor's scripts/gate/).

    docgate.py check [repo]              # all checks; exit 1 and list every problem
    docgate.py stamp <page> [--stamp]    # what changed under a page's Sources since Verified; --stamp sets it to now

Config `.framework.json` at the repo root, every key optional (a `*` in a pattern spans directories):
    {"mirrors":   {"sources": ["src/*.py"], "exclude": ["src/tests/*"]},
     "freshness": {"folders": ["docs/guides", "docs/features"], "exempt": ["docs/guides/checklist.md"]},
     "links":     {"skip": ["docs/decisions/", "docs/history/"]}}

Checks: docs/brief.md exists; every mirrored source has docs/code/<path>.md and every mirror a source; every `docs/...` path mentioned
exists; every page in the freshness folders has `> Verified: DATE · Sources: `path`, ...` and is not older than its Sources, has no
placeholder, names only real paths and real script flags, and is listed in docs/README.md.
Stamp only after re-reading the page against the listed changes: a stamp on an unread page is a lie this gate cannot see.
"""
import datetime
import fnmatch
import json
import os
import re
import subprocess
import sys

HEADER = re.compile(r"^> Verified: (\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2})? · Sources: (.+)$")
SPAN = re.compile(r"`([^`\n]+)`")
DOC_PATH = re.compile(r"docs/[\w.\-/]+\.(?:md|png|svg|py|sh|json|pptx)")
PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME)\b|(?i:coming soon)")
SCRIPT_EXT = (".sh", ".py", ".mjs", ".js")
TEXT_EXT = (".md", ".mdc", ".txt", ".json", ".toml", ".py", ".sh", ".js", ".mjs", ".ts", ".rs", ".swift", ".c", ".h", ".go")
DEFAULT_SKIP = ["docs/decisions/", "docs/history/"]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.rstrip()


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def load_config(root):
    path = os.path.join(root, ".framework.json")
    return json.loads(read(path)) if os.path.exists(path) else {}


def repo_files(root):
    """Tracked plus untracked-but-not-ignored files that exist."""
    listed = git(root, "ls-files", "-co", "--exclude-standard").splitlines()
    return [f for f in listed if os.path.isfile(os.path.join(root, f))]


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def check_brief(root, files, config):
    return [] if "docs/brief.md" in files else ["docs/brief.md: missing (mission, non-goals, priorities; see the adopt-framework skill)"]


def check_mirrors(root, files, config):
    spec = config.get("mirrors") or {}
    if not spec.get("sources"):
        return []
    sources = {f for f in files if matches(f, spec["sources"]) and not matches(f, spec.get("exclude", []))}
    mirrors = {f[len("docs/code/"):-3] for f in files if f.startswith("docs/code/") and f.endswith(".md")}
    problems = [f"{s}: no doc mirror at docs/code/{s}.md" for s in sorted(sources - mirrors)]
    problems += [f"docs/code/{m}.md: mirror without a source file" for m in sorted(mirrors - sources)]
    return problems


def mention_is_pattern(text, match):
    return any(mark in text[max(match.start() - 1, 0):match.end() + 1] for mark in "<*")


def check_links(root, files, config):
    skip = (config.get("links") or {}).get("skip", DEFAULT_SKIP)
    problems = []
    for rel in files:
        if rel.startswith(tuple(skip)) or not rel.endswith(TEXT_EXT):
            continue
        text = read(os.path.join(root, rel))
        for match in DOC_PATH.finditer(text):
            if not mention_is_pattern(text, match) and not os.path.exists(os.path.join(root, match.group(0))):
                problems.append(f"{rel}: `{match.group(0)}` does not exist")
    return sorted(set(problems))


def freshness_pages(files, config):
    spec = config.get("freshness") or {}
    folders = spec.get("folders", ["docs/guides", "docs/features"])
    exempt = set(spec.get("exempt", []))
    pages = [f for f in files if f.endswith(".md") and os.path.dirname(f) in folders]
    return sorted(pages), exempt


def parse_header(text):
    for line in text.splitlines()[:15]:
        match = HEADER.match(line)
        if match:
            return match.group(1), SPAN.findall(match.group(2))
    return None


def dirty_paths(root):
    out = git(root, "status", "--porcelain", "-uall")
    return {line[3:].split(" -> ")[-1] for line in out.splitlines()}


def is_dirty(path, dirty):
    prefix = path.rstrip("/") + "/"
    return any(d == path or d.startswith(prefix) for d in dirty)


def last_commit(root, paths):
    return git(root, "log", "-1", "--format=%H %cs", "--", *paths).split()


def is_ancestor(root, older, newer):
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=root).returncode == 0


def header_problems(root, rel, header, ctx):
    verified, sources = header
    problems = [f"{rel}: header lists no Sources"] if not sources else []
    if verified > ctx["today"]:
        problems.append(f"{rel}: Verified {verified} is in the future")
    missing = [s for s in sources if not os.path.exists(os.path.join(root, s))]
    problems += [f"{rel}: Source `{s}` does not exist" for s in missing]
    present = [s for s in sources if s not in missing]
    return problems + (staleness_problems(root, rel, verified, present, ctx) if present else [])


def staleness_problems(root, rel, verified, sources, ctx):
    doc_dirty = is_dirty(rel, ctx["dirty"])
    if any(is_dirty(s, ctx["dirty"]) for s in sources):
        if not doc_dirty:
            return [f"{rel}: a Source has uncommitted changes but the page is not updated with it"]
        if verified != ctx["today"]:
            return [f"{rel}: a Source has uncommitted changes; re-read the page and stamp it today"]
    src, doc = last_commit(root, sources), last_commit(root, [rel])
    if not src or doc_dirty:
        return []
    if not doc or not is_ancestor(root, src[0], doc[0]):
        return [f"{rel}: Sources changed on {src[1]} after the page was last touched (docgate.py stamp {rel})"]
    if verified < src[1]:
        return [f"{rel}: Verified {verified} is older than the last Source change {src[1]}"]
    return []


def path_token(span, tops):
    words = span.split()
    token = words[0] if words else ""
    if not token.startswith(tops) or any(c in token for c in "<>*{}$~"):
        return None
    return re.sub(r"(::\w+|:\d+(-\d+)?)$", "", token.rstrip(".,;:)")).rstrip("/")


def flag_problems(root, rel, number, token, span):
    source = read(os.path.join(root, token))
    if '"$@"' in source or "sys.argv[1:]" in source:  # forwards its arguments elsewhere
        return []
    flags = re.findall(r"(?<![\w-])--[a-z][\w-]*", span)
    return [f"{rel}:{number}: `{token}` has no {flag} option" for flag in flags if flag not in source]


def span_problems(root, rel, number, span, tops):
    token = path_token(span, tops)
    if token is None:
        return []
    full = os.path.join(root, token)
    if not os.path.exists(full):
        return [f"{rel}:{number}: `{token}` does not exist"]
    return flag_problems(root, rel, number, token, span) if token.endswith(SCRIPT_EXT) and os.path.isfile(full) else []


def body_problems(root, rel, text, tops):
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER.search(line):
            problems.append(f"{rel}:{number}: placeholder text (planned work belongs in docs/todo.md or docs/plans/)")
        if not line.startswith("> Verified:"):
            for span in SPAN.findall(line):
                problems += span_problems(root, rel, number, span, tops)
    return problems


def check_page(root, rel, exempt, ctx):
    text = read(os.path.join(root, rel))
    header = parse_header(text)
    problems = []
    if rel not in exempt:
        problems = header_problems(root, rel, header, ctx) if header else [f"{rel}: no `> Verified: YYYY-MM-DD · Sources: `path`` header in the first 15 lines"]
    if rel not in ctx["map"]:
        problems.append(f"docs/README.md: does not list {rel}")
    return problems + body_problems(root, rel, text, ctx["tops"])


def map_mentions(root, pages):
    path = os.path.join(root, "docs/README.md")
    text = read(path) if os.path.exists(path) else ""
    stem = lambda rel: os.path.basename(rel)[:-3]
    return {rel for rel in pages if f"`{rel}`" in text or f"`{stem(rel)}`" in text or f"({rel[5:]})" in text}


def check_freshness(root, files, config):
    pages, exempt = freshness_pages(files, config)
    if not pages:
        return []
    tops = tuple(sorted({f.split("/")[0] + "/" for f in files if "/" in f}))
    ctx = {"today": datetime.date.today().isoformat(), "dirty": dirty_paths(root), "tops": tops, "map": map_mentions(root, pages)}
    problems = []
    for rel in pages:
        problems += check_page(root, rel, exempt, ctx)
    return problems


CHECKS = (check_brief, check_mirrors, check_links, check_freshness)


def run_checks(root):
    files, config = repo_files(root), load_config(root)
    problems = []
    for check in CHECKS:
        problems += check(root, files, config)
    return problems


def repo_root(start):
    return git(start, "rev-parse", "--show-toplevel") or None


def cmd_check(argv):
    root = repo_root(argv[0] if argv else os.getcwd())
    if not root:
        print("docgate: not inside a git repository")
        return 2
    problems = run_checks(root)
    print("\n".join(["Doc gate problems:"] + problems) if problems else "doc gate: ok")
    return 1 if problems else 0


def cmd_stamp(argv):
    pages = [a for a in argv if not a.startswith("--")]
    if len(pages) != 1:
        print(__doc__)
        return 2
    full = os.path.abspath(pages[0])
    root = repo_root(os.path.dirname(full))
    rel = os.path.relpath(full, root)
    text = read(full)
    header = parse_header(text)
    if header is None:
        print(f"{rel}: no header line; add `> Verified: YYYY-MM-DD · Sources: `path`` first")
        return 1
    verified, sources = header
    print(f"{rel}: verified {verified}; sources: {', '.join(sources)}")
    log = git(root, "log", f"--since={verified} 00:00", "--stat", "--format=== %h %cs %s", "--", *sources)
    print(log or "no commits under the sources since then")
    dirty = [s for s in sources if is_dirty(s, dirty_paths(root))]
    if dirty:
        print("uncommitted changes under: " + ", ".join(dirty))
    if "--stamp" in argv:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        text = re.sub(r"^> Verified: \d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?", f"> Verified: {now}", text, count=1, flags=re.M)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"stamped {now}")
    return 0


def main(argv):
    commands = {"check": cmd_check, "stamp": cmd_stamp}
    if not argv or argv[0] not in commands:
        print(__doc__)
        return 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
