"""The account-bound call sites are a closed list: a new `auth=True` call must be added here, on purpose."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]

# (file relative to src/, enclosing function). Keep the cookie policy docs in step.
ACCOUNT_BOUND = {
    ("ytdlp.py", "_list_subscribed_channels"),
    ("tui/screens/mixins/feed_loader.py", "_load_feed"),
    ("tui/screens/mixins/feed_loader.py", "_open_cursor"),
}


def _auth_true_sites() -> set[tuple[str, str]]:
    found = set()
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("tests/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.keyword) and node.arg == "auth" and getattr(node.value, "value", None) is True:
                    found.add((rel, fn.name))
    return found


def test_auth_true_call_sites_are_the_known_list():
    assert _auth_true_sites() == ACCOUNT_BOUND


def test_no_cookie_header_or_browser_option_elsewhere():
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("tests/") or rel in ("config.py", "cookies.py"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "cookiesfrombrowser" not in text, rel
