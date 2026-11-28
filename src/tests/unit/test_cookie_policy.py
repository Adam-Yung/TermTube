"""The account-bound call sites are a closed list: a new `auth=True` call must be added here, on purpose."""

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]

# (file relative to src/, enclosing function). Keep the cookie policy docs in step.
ACCOUNT_BOUND = {
    ("ytdlp.py", "_list_subscribed_channels"),
    ("tui/screens/mixins/feed_loader.py", "_load_feed"),
    ("tui/screens/mixins/feed_loader.py", "_open_cursor"),
}


def _sources() -> Iterator[tuple[str, Path]]:
    """(path relative to src/, path) of every product source file."""
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if not rel.startswith("tests/"):
            yield rel, path


def _passes_auth_true(fn: ast.AST) -> bool:
    return any(
        isinstance(node, ast.keyword) and node.arg == "auth" and getattr(node.value, "value", None) is True
        for node in ast.walk(fn)
    )


def _auth_true_sites() -> set[tuple[str, str]]:
    return {
        (rel, fn.name)
        for rel, path in _sources()
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and _passes_auth_true(fn)
    }


def test_auth_true_call_sites_are_the_known_list():
    assert _auth_true_sites() == ACCOUNT_BOUND


def test_no_cookie_header_or_browser_option_elsewhere():
    for rel, path in _sources():
        if rel in ("config.py", "cookies.py"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "cookiesfrombrowser" not in text, rel
