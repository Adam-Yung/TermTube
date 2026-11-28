"""``theme.tcss`` may only style what the app composes: a selector that matches nothing is a rule that rots."""

import importlib
import pkgutil
import re
from collections import Counter
from pathlib import Path

from textual.dom import DOMNode
from textual.widgets import Footer, ProgressBar

import src.tui

TUI = Path(__file__).resolve().parents[2] / "tui"
THEME_PREFIX = "theme-"
# textual loads widgets lazily: naming these registers the subclasses the selector scan reads.
LAZY_WIDGETS = (Footer, ProgressBar)

for _mod in pkgutil.walk_packages(src.tui.__path__, "src.tui."):
    importlib.import_module(_mod.name)


def _all_subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


def _selectors() -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", (TUI / "theme.tcss").read_text(encoding="utf-8"), flags=re.S)
    return [m.group(1).strip() for m in re.finditer(r"([^{}]*)\{", css) if m.group(1).strip()]


def _py() -> str:
    return "".join(p.read_text(encoding="utf-8") for p in TUI.rglob("*.py"))


def test_no_selector_block_is_written_twice():
    counts = Counter(_selectors())
    assert [s for s, n in counts.items() if n > 1] == []


def test_every_id_selector_names_a_composed_widget():
    ids = set(re.findall(r"""\bid=f?["']([^"']+)["']""", _py()))
    patterns = [re.compile(re.sub(r"\{[^}]*\}", r"[\\w-]+", i) + "$") for i in ids]
    wanted = set(re.findall(r"#([a-zA-Z][\w-]*)", " ".join(_selectors())))
    assert [i for i in wanted if not any(p.match(i) for p in patterns)] == []


def test_every_type_selector_names_a_real_widget_or_screen():
    known = {c.__name__ for c in _all_subclasses(DOMNode)} | {"App", "Screen"}
    text = re.sub(r"[#.][\w-]+|:[\w-]+(\([^)]*\))?", "", " ".join(_selectors()))
    wanted = set(re.findall(r"\b[A-Z][A-Za-z]+\b", text))
    assert sorted(wanted - known) == []


def test_every_class_selector_is_added_by_code_or_is_a_component_class():
    py = _py()
    wanted = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"#[\w-]+", "", " ".join(_selectors()))))
    wanted = {c for c in wanted if "--" not in c}
    unused = [c for c in wanted if c not in py and not (c.startswith(THEME_PREFIX) and f'"{THEME_PREFIX}{{' in py)]
    assert unused == []


def test_every_queried_id_is_composed_somewhere():
    py = _py()
    ids = set(re.findall(r"""\bid=f?["']([^"']+)["']""", py))
    patterns = [re.compile(re.sub(r"\{[^}]*\}", r"[\\w-]+", i) + "$") for i in ids]
    queried = set(re.findall(r"""\bquery(?:_one)?\(\s*f?["']#([\w{}-]+)""", py))
    assert [q for q in queried if not any(p.match(q) for p in patterns)] == []
