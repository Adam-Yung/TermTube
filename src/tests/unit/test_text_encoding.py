"""Every text file the app reads or writes names its encoding.

The app writes UTF-8 (titles are not ASCII). Windows reads with the locale codec (cp1252) unless Python is in
UTF-8 mode, which only termtube.cmd turns on. A bare ``read_text()`` therefore raised UnicodeDecodeError on the first
accented title when the app was started any other way, and the loaders did not catch it. CI found it on Windows.
"""

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
THIS_FILE = Path(__file__).resolve()


def text_calls_without_encoding(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or "encoding" in {k.arg for k in node.keywords}:
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
            yield node.lineno, func.attr
        elif isinstance(func, ast.Name) and func.id == "open":
            keyword_mode = next((k.value for k in node.keywords if k.arg == "mode"), None)
            mode = node.args[1] if len(node.args) > 1 else keyword_mode
            if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value):
                yield node.lineno, "open"


def test_no_text_file_access_relies_on_the_locale_codec():
    offenders = []
    for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]:
        if path.resolve() != THIS_FILE:
            offenders += [f"{path.relative_to(ROOT)}:{line} {what}" for line, what in text_calls_without_encoding(path)]
    assert not offenders, "pass encoding='utf-8':\n" + "\n".join(offenders)


@pytest.mark.skipif(sys.platform == "win32", reason="needs an ASCII locale via env vars Windows ignores")
def test_history_round_trips_non_ascii_under_a_non_utf8_locale(tmp_path):
    """The behaviour behind the lint: history survives non-ASCII with UTF-8 mode off and an ASCII locale."""
    script = textwrap.dedent(
        f"""
        import locale, sys
        sys.path.insert(0, {str(ROOT)!r})
        assert sys.flags.utf8_mode == 0
        assert locale.getpreferredencoding(False).lower() in ("ascii", "ansi_x3.4-1968", "us-ascii")
        from src import history
        history.add({{"id": "AAAAAAAAAAA", "title": "Žižek ā 音楽"}})
        history._cache = None
        assert history.all_entries()[0]["title"] == "Žižek ā 音楽"
        print("ROUND-TRIP-OK")
        """
    )
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", LC_ALL="C", LANG="C",
               XDG_CONFIG_HOME=str(tmp_path / "cfg"), TERMTUBE_CACHE_DIR=str(tmp_path / "cache"))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=60)
    assert "ROUND-TRIP-OK" in result.stdout, result.stdout + result.stderr
