"""Long comment blocks, long files and suppression comments, in every language."""
import re

import comment_lines
import lib

SAFETY = re.compile(r"^\s*///\s*# Safety\b")
SUPPRESSION = re.compile(
    r"(#|//|/\*)\s*(noqa\b|swiftlint:disable|eslint-disable|shellcheck\s+disable=|type:\s*ignore|@ts-ignore|@ts-nocheck|nolint\b)"
    r"|^\s*#!?\[allow\("
)


def blocks(numbers):
    """Runs of consecutive line numbers as (first, last)."""
    runs = []
    for number in sorted(numbers):
        if runs and runs[-1][1] == number - 1:
            runs[-1] = (runs[-1][0], number)
        else:
            runs.append((number, number))
    return runs


def exempt(repo, path, lines, first, last):
    """A short file header, or a Rust safety section the language's conventions ask for."""
    at_top = all(not line.strip() or line.startswith("#!") for line in lines[: first - 1])
    if at_top and last - first + 1 <= repo.caps["header_comment"]:
        return True
    return path.endswith(".rs") and any(SAFETY.match(line) for line in lines[first - 1 : last])


def comment_blocks(repo, path, text):
    lines = text.splitlines()
    found = []
    for first, last in blocks(comment_lines.of(repo.language(path), path, text)):
        size = last - first + 1
        if size >= repo.caps["comment_block"] and not exempt(repo, path, lines, first, last):
            found.append(lib.Violation("comment-block", path, first, f"{size} comment lines (move to the code's doc)"))
    return found


def suppressions(path, text):
    return [
        lib.Violation("suppression", path, number, "suppression comment: fix the code instead")
        for number, line in enumerate(text.splitlines(), 1)
        if SUPPRESSION.search(line)
    ]


def violations(repo):
    found = []
    for path in repo.sources():
        text = repo.read(path)
        found += comment_blocks(repo, path, text) + suppressions(path, text)
        count = len(text.splitlines())
        if count > repo.caps["file_lines"]:
            found.append(lib.Violation("file-lines", path, 1, f"{count} lines, over {repo.caps['file_lines']}"))
    return found
