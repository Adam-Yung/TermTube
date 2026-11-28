"""What the working tree changed against HEAD: staged, unstaged and untracked."""
import lib


def untracked(root):
    return [p for p in lib.git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0") if p]


def changed(root):
    out = lib.git(root, "diff", "-z", "--name-only", "--no-renames", "HEAD")
    return {p for p in out.split("\0") if p} | set(untracked(root))


def line_deltas(root):
    """Net lines added per file; a rename counts only its edits, an untracked file counts in full."""
    deltas = {}
    records = iter(lib.git(root, "diff", "-z", "--numstat", "-M", "HEAD").split("\0"))
    for record in filter(None, records):
        added, removed, path = record.split("\t", 2)
        if not path:  # a rename: the old and new names follow as their own records
            next(records)
            path = next(records)
        if added != "-":
            deltas[path] = int(added) - int(removed)
    for path in untracked(root):
        if (root / path).is_file():
            deltas[path] = len(lib.read(root, path).splitlines())
    return deltas
