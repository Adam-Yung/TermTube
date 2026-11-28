"""Swift funcs and types whose name no other non-test code uses."""
import re
from collections import Counter

import config
import lib

STRING_OR_COMMENT = re.compile(r'("(?:\\.|[^"\\\n])*")|//[^\n]*|/\*.*?\*/', re.S)
DECLARATION = re.compile(r"\b(func|class|struct|enum|protocol|actor|typealias)[ \t]+([A-Za-z_]\w*)")
EXTENSION = re.compile(r"\bextension[ \t]+([A-Za-z_]\w*)")
WORD = re.compile(r"[A-Za-z_]\w*")
PROTOCOL = re.compile(r"\bprotocol[ \t]+\w+[^{]*\{")
# Called by the language, a framework or the runtime, never by name from our code.
EXEMPT_MARKS = re.compile(r"\boverride\b|@objc\b|@IBAction\b|@main\b|@_cdecl\b|\boperator\b")
EXEMPT_NAMES = {
    "main", "var", "let", "func", "CodingKeys", "hash", "encode", "body", "callAsFunction", "makeBody", "makeNSView",
    "updateNSView", "makeUIView", "updateUIView", "makeNSViewController", "updateNSViewController", "makeCoordinator",
    "dismantleNSView", "sizeThatFits", "placeSubviews", "path", "reduce", "next", "makeIterator", "makeAsyncIterator",
}
DELEGATE = re.compile(
    r"^(application|window|menu|tableView|outlineView|collectionView|urlSession|userNotificationCenter|listener|control"
    r"|text|webView|scene|draggingEntered|performDrag|numberOfRows|animationDid)(?![a-z])"
)


def code_only(text):
    """Comments blanked, strings kept (interpolation is a use), line numbers unchanged."""
    return STRING_OR_COMMENT.sub(lambda m: m.group(1) or "\n" * m.group(0).count("\n"), text)


def block_end(text, start):
    depth = 0
    for index in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return index
    return len(text)


def requirements(text):
    """Names a protocol of ours declares: implementations are reached through the protocol."""
    names = set()
    for found in PROTOCOL.finditer(text):
        body = text[found.end() : block_end(text, found.end() - 1)]
        names.update(name for _, name in DECLARATION.findall(body))
    return names


def marked(lines, number):
    """The declaration line, or an attribute on its own line above it, says someone else calls it."""
    above = lines[number - 2].strip() if number > 1 else ""
    return bool(EXEMPT_MARKS.search(lines[number - 1]) or (above.startswith("@") and EXEMPT_MARKS.search(above)))


def exempt(name):
    return name in EXEMPT_NAMES or name.startswith("test") or bool(DELEGATE.match(name))


def declarations(text):
    lines = text.splitlines()
    for found in DECLARATION.finditer(text):
        number = text.count("\n", 0, found.start()) + 1
        name = found.group(2)
        if not exempt(name) and not marked(lines, number):
            yield name, number


def uses(sources):
    """How often each name appears other than as a declaration or the head of an extension."""
    words = Counter()
    for text in sources.values():
        words.update(WORD.findall(text))
        words.subtract(name for _, name in DECLARATION.findall(text))
        words.subtract(EXTENSION.findall(text))
    return words


def finding(path, name, line, tested):
    if name in tested:
        return lib.Violation("swift-test-only", path, line, f"only tests use `{name}`")
    return lib.Violation("swift-unused", path, line, f"nothing uses `{name}`")


def violations(repo):
    swift = repo.sources("swift")
    sources = {p: code_only(repo.read(p)) for p in swift
               if not config.is_test(p) and not p.endswith("Package.swift")}
    used = uses(sources)
    tested = {w for p in swift if config.is_test(p) for w in WORD.findall(code_only(repo.read(p)))}
    reached = set().union(*map(requirements, sources.values()), set())
    return [
        finding(path, name, line, tested)
        for path, text in sources.items()
        for name, line in declarations(text)
        if used[name] <= 0 and name not in reached
    ]
