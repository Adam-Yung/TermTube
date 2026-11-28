#!/usr/bin/env python3
"""Every feature page names the objectives it serves and the code it owns; no source file is unowned.

    check-features.py                  judges the feature pages against the objectives and the tree
    check-features.py --list-unowned   prints the source files no page owns, and nothing else
"""
import re
import sys

import config
import feature_pages
import lib


def unowned(repo, pages):
    patterns = [lib.glob_pattern(glob) for page in pages for glob in page.owns]
    return [path for path in repo.product_files() if not any(p.match(path) for p in patterns)]


def serves_problems(page, objectives):
    if not page.serves:
        return [f"{page.path}: no `> Serves:` line in its first 15 lines"]
    return [f"{page.path}: Serves unknown objective `{i}`" for i in page.serves if i not in objectives]


def catch_all(repo, glob):
    """A glob with no fixed part, or one naming a whole top-level folder, claims everything and tells nothing."""
    fixed = re.split(r"[*?]", glob)[0].strip("/")
    if not fixed:
        return True
    tops = {p.split("/")[0] for p in repo.product_files() if "/" in p}
    return fixed in tops and glob.strip("/*") == fixed


def glob_problem(repo, page, glob):
    if catch_all(repo, glob):
        return f"{page.path}: Owns `{glob}` is a catch-all; name the folders or files of this feature"
    if not any(lib.glob_pattern(glob).match(path) for path in repo.files()):
        return f"{page.path}: Owns `{glob}` matches nothing"
    return None


def owns_problems(repo, page):
    if not page.owns:
        return [f"{page.path}: no `> Owns:` line in its first 15 lines"]
    return [p for p in (glob_problem(repo, page, glob) for glob in page.owns) if p]


def index_problems(repo, pages):
    index = f"{repo.cfg['feature_dir']}/README.md"
    if not (repo.root / index).is_file():
        return [f"{index}: missing"]
    text = repo.read(index)
    return [f"{index}: does not list {page.name}" for page in pages
            if not re.search(rf"(?<![\w-]){re.escape(page.name)}", text)]


def check(repo):
    objectives = feature_pages.objectives(repo)
    pages = feature_pages.load(repo)
    problems = [line for page in pages for line in serves_problems(page, objectives) + owns_problems(repo, page)]
    problems += index_problems(repo, pages)
    problems += [f"{path}: owned by no feature page" for path in unowned(repo, pages)]
    return lib.verdict(problems, "features")


def list_unowned(repo):
    for path in unowned(repo, feature_pages.load(repo)):
        print(path)
    return 0


def main(argv=None):
    made = lib.parser(__doc__)
    made.add_argument("--list-unowned", action="store_true")
    args = made.parse_args(argv)
    body = list_unowned if args.list_unowned else check
    return lib.main_guard(lambda: body(config.open_repo(args)))


if __name__ == "__main__":
    sys.exit(main())
