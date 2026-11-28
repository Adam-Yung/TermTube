"""Which lines of a source file hold nothing but a comment, per language."""
import io
import re
import tokenize

import lib

HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*\\?['\"]?([A-Za-z_]\w*)")


def python_lines(path, text):
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        raise lib.GateError(f"{path}: does not tokenize")
    return {t.start[0] for t in tokens if t.type == tokenize.COMMENT and t.line.lstrip().startswith("#")}


def hash_lines(text):
    found, until = set(), None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if until:
            until = None if stripped == until else until
        elif stripped.startswith("#"):
            found.add(number)
        else:
            opened = HEREDOC.search(line)
            until = opened.group(1) if opened else None
    return found


def slash_lines(text):
    found, inside = set(), False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if inside or stripped.startswith("/*"):
            found.add(number)
            inside = "*/" not in stripped
        elif stripped.startswith("//"):
            found.add(number)
    return found


def of(language, path, text):
    if language == "python":
        found = python_lines(path, text)
    elif language in ("shell", "ruby"):
        found = hash_lines(text)
    else:
        found = slash_lines(text)
    if text.startswith("#!"):
        found.discard(1)
    return found
