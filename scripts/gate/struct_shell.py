"""Shell warnings, errors and unquoted expansions, by shellcheck. A file with no shebang is read as bash."""
import json

import lib

# Info level upstream, but a refactor that drops quotes shows up only here.
QUOTING = (2048, 2086)


def counted(comment):
    return comment["level"] in ("warning", "error") or comment["code"] in QUOTING


def check(repo, files, extra):
    if not files:
        return []
    cmd = [lib.tool("shellcheck"), "--norc", "--severity=info", "--format=json1", *extra]
    done = lib.run(cmd + files, repo.root, timeout=300, ok=(0, 1))
    return [
        lib.Violation(f"sh:SC{v['code']}", v["file"], v["line"], v["message"])
        for v in json.loads(done.stdout)["comments"]
        if counted(v)
    ]


def violations(repo):
    files = repo.sources("shell")
    bare = [p for p in files if not repo.read(p).startswith("#!")]
    return check(repo, [p for p in files if p not in bare], []) + check(repo, bare, ["--shell=bash"])
