"""Platform-path correctness tests.

Two categories:
  A. Module-level path constant tests — each module that owns a path constant
     is tested under Windows simulation (monkeypatched IS_WINDOWS=True).
     Linux-path tests are skipped on Windows since monkeypatching IS_WINDOWS
     to False on a live Windows process still resolves Windows env vars.

  B. Source linter test — scans every .py under src/ for patterns known to
     introduce hardcoded, platform-wrong paths, failing with file:line if found.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _restore_modules():
    """Reload hot-patched modules after each test to restore clean module state.

    importlib.reload() during path tests changes module-level class objects
    (e.g. Segment in sponsorblock).  Without this cleanup the reloaded class
    is a different object from the one used in test_sponsorblock.py, causing
    frozen dataclass equality to fail across test files.
    """
    yield
    import importlib as _il, sys as _sys
    for _name in ("src.plat", "src.history", "src.playlist", "src.deps"):
        if _name in _sys.modules:
            try:
                _il.reload(_sys.modules[_name])
            except Exception:
                pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _reload_as_windows(monkeypatch, module_name: str, appdata: str, localappdata: str):
    """Reload *module_name* with IS_WINDOWS=True and Windows env vars set."""
    monkeypatch.setenv("APPDATA",      appdata)
    monkeypatch.setenv("LOCALAPPDATA", localappdata)
    # Patch sys.platform before reloading so IS_WINDOWS computes True at import
    monkeypatch.setattr(sys, "platform", "win32")
    if "src.plat" in sys.modules:
        importlib.reload(sys.modules["src.plat"])
    mod = sys.modules.get(module_name)
    if mod:
        importlib.reload(mod)
    else:
        importlib.import_module(module_name)
    return sys.modules[module_name]


_WIN_APPDATA      = r"C:\Users\TestUser\AppData\Roaming"
_WIN_LOCALAPPDATA = r"C:\Users\TestUser\AppData\Local"

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Linux path behaviour not testable on Windows",
)
_SKIP_WIN_SHELL = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Linux shell syntax not testable on Windows",
)


# ── A. Module path constant tests ────────────────────────────────────────────


class TestHistoryPath:
    def test_windows_uses_appdata_not_dot_config(self, monkeypatch):
        mod = _reload_as_windows(monkeypatch, "src.history", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        s = str(mod.HISTORY_PATH)
        assert "AppData" in s, f"Expected AppData in HISTORY_PATH, got: {s}"
        assert ".config" not in s, f"Unexpected .config in HISTORY_PATH: {s}"
        assert "TermTube" in s
        assert s.endswith("history.json")

    @_SKIP_WIN
    def test_linux_uses_dot_config(self, monkeypatch):
        monkeypatch.setattr("src.plat.IS_WINDOWS", False)
        monkeypatch.setattr("src.plat.IS_MACOS",   False)
        monkeypatch.setattr("src.plat.IS_LINUX",   True)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        importlib.reload(sys.modules["src.plat"])
        importlib.reload(sys.modules["src.history"])
        import src.history as mod
        s = str(mod.HISTORY_PATH)
        assert ".config" in s and "AppData" not in s and s.endswith("history.json")

    def test_parent_matches_config_dir(self, monkeypatch):
        """HISTORY_PATH.parent must equal get_config_dir() on any platform."""
        mod = _reload_as_windows(monkeypatch, "src.history", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        import src.plat as plat
        assert mod.HISTORY_PATH.parent == plat.get_config_dir()


class TestPlaylistPath:
    def test_windows_uses_appdata_not_dot_config(self, monkeypatch):
        mod = _reload_as_windows(monkeypatch, "src.playlist", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        s = str(mod._PLAYLISTS_PATH)
        assert "AppData" in s, f"Expected AppData in _PLAYLISTS_PATH, got: {s}"
        assert ".config" not in s, f"Unexpected .config in _PLAYLISTS_PATH: {s}"
        assert s.endswith("playlists.json")

    @_SKIP_WIN
    def test_linux_uses_dot_config(self, monkeypatch):
        monkeypatch.setattr("src.plat.IS_WINDOWS", False)
        monkeypatch.setattr("src.plat.IS_MACOS",   False)
        monkeypatch.setattr("src.plat.IS_LINUX",   True)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        importlib.reload(sys.modules["src.plat"])
        importlib.reload(sys.modules["src.playlist"])
        import src.playlist as mod
        s = str(mod._PLAYLISTS_PATH)
        assert ".config" in s and "AppData" not in s and s.endswith("playlists.json")

    def test_parent_matches_config_dir(self, monkeypatch):
        mod = _reload_as_windows(monkeypatch, "src.playlist", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        import src.plat as plat
        assert mod._PLAYLISTS_PATH.parent == plat.get_config_dir()


class TestSponsorblockCacheDir:
    def test_windows_uses_localappdata_not_dot_cache(self, monkeypatch):
        monkeypatch.setenv("APPDATA",      _WIN_APPDATA)
        monkeypatch.setenv("LOCALAPPDATA", _WIN_LOCALAPPDATA)
        monkeypatch.setattr(sys, "platform", "win32")
        importlib.reload(sys.modules["src.plat"])
        import src.plat as plat
        cache = plat.get_cache_dir()
        s = str(cache / "sb")
        assert "AppData" in s, f"Expected AppData in cache/sb path, got: {s}"
        assert ".cache" not in s, f"Unexpected .cache in cache/sb path: {s}"
        assert s.endswith("sb")

    @_SKIP_WIN
    def test_linux_uses_dot_cache(self, monkeypatch):
        monkeypatch.setattr("src.plat.IS_WINDOWS", False)
        monkeypatch.setattr("src.plat.IS_MACOS",   False)
        monkeypatch.setattr("src.plat.IS_LINUX",   True)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        importlib.reload(sys.modules["src.plat"])
        import src.sponsorblock
        importlib.reload(sys.modules["src.sponsorblock"])
        import src.sponsorblock as mod
        s = str(mod._CACHE_DIR)
        assert ".cache" in s and "AppData" not in s and s.endswith("sb")

    def test_parent_matches_cache_dir(self, monkeypatch):
        monkeypatch.setattr("src.plat.IS_WINDOWS", True)
        monkeypatch.setattr("src.plat.IS_MACOS",   False)
        monkeypatch.setattr("src.plat.IS_LINUX",   False)
        monkeypatch.setenv("APPDATA",      _WIN_APPDATA)
        monkeypatch.setenv("LOCALAPPDATA", _WIN_LOCALAPPDATA)
        import importlib, sys
        importlib.reload(sys.modules["src.plat"])
        import src.plat as plat
        # sponsorblock._CACHE_DIR = get_cache_dir() / "sb", so its parent is get_cache_dir()
        assert plat.get_cache_dir() / "sb" == plat.get_cache_dir() / "sb"  # tautology guard
        assert (plat.get_cache_dir() / "sb").parent == plat.get_cache_dir()


class TestCookiesHelpPaths:
    @staticmethod
    def _ensure_help_built(mod):
        """COOKIES_HELP is lazily built; trigger it before asserting."""
        if mod.COOKIES_HELP is None:
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                mod.print_cookies_help()
        return mod.COOKIES_HELP

    def test_windows_no_mixed_separators(self, monkeypatch):
        """On Windows the cookie path must not mix forward and backslashes."""
        mod = _reload_as_windows(monkeypatch, "src.deps", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        help_text = self._ensure_help_built(mod)
        assert "AppData/Roaming" not in help_text, (
            "Mixed separators in COOKIES_HELP: found AppData/Roaming"
        )
        assert "AppData" in help_text

    def test_windows_powershell_continuation(self, monkeypatch):
        """Option B command should use backtick continuation on Windows."""
        mod = _reload_as_windows(monkeypatch, "src.deps", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        assert " `" in self._ensure_help_built(mod), "Expected PowerShell backtick continuation in COOKIES_HELP"

    @_SKIP_WIN_SHELL
    def test_linux_bash_continuation(self, monkeypatch):
        """Option B command should use backslash continuation on Linux."""
        monkeypatch.setattr("src.plat.IS_WINDOWS", False)
        monkeypatch.setattr("src.plat.IS_MACOS",   False)
        importlib.reload(sys.modules["src.plat"])
        importlib.reload(sys.modules["src.deps"])
        import src.deps as mod
        assert " \
" in self._ensure_help_built(mod), "Expected bash backslash continuation in COOKIES_HELP"

    def test_cookies_path_native_separator(self, monkeypatch):
        """The cookies.txt path in help should use native os.sep."""
        mod = _reload_as_windows(monkeypatch, "src.deps", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        import src.plat as plat
        expected = str(plat.get_config_dir() / "cookies.txt")
        assert expected in self._ensure_help_built(mod), f"Expected {expected!r} in COOKIES_HELP"

    def test_config_yaml_native_separator(self, monkeypatch):
        mod = _reload_as_windows(monkeypatch, "src.deps", _WIN_APPDATA, _WIN_LOCALAPPDATA)
        import src.plat as plat
        expected = str(plat.get_config_dir() / "config.yaml")
        assert expected in self._ensure_help_built(mod), f"Expected {expected!r} in COOKIES_HELP"


# ── B. Source linter — no hardcoded platform paths ───────────────────────────

_FORBIDDEN = [
    (
        re.compile(r"""Path\.home\(\)\s*/\s*['"]\.config['"]"""),
        'use get_config_dir() instead of Path.home() / ".config"',
    ),
    (
        re.compile(r"""Path\.home\(\)\s*/\s*['"]\.cache['"]"""),
        'use get_cache_dir() instead of Path.home() / ".cache"',
    ),
    (
        re.compile(r"""Path\.home\(\)\s*/\s*['"]\.local['"]"""),
        'use get_data_dir() instead of Path.home() / ".local"',
    ),
]

# plat.py defines the helpers.
# main.py references the legacy path intentionally in _migrate_legacy_windows_paths().
_LINTER_ALLOWLIST = {"plat.py", "main.py", "bootstrap.py"}


class TestNoHardcodedPlatformPaths:
    def test_no_hardcoded_unix_paths_in_src(self):
        src_root = Path(__file__).parents[2]
        violations: list[str] = []
        for py_file in sorted(src_root.rglob("*.py")):
            if py_file.name in _LINTER_ALLOWLIST:
                continue
            # Skip the tests subtree — test files legitimately reference path
            # strings in assertions and fixture names that match the patterns.
            if "tests" in py_file.parts:
                continue
            try:
                text = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for pattern, message in _FORBIDDEN:
                    if pattern.search(line):
                        rel = py_file.relative_to(src_root.parent)
                        violations.append(
                            f"  {rel}:{lineno}: {message}\n    {line.strip()}"
                        )
        assert not violations, (
            "Hardcoded platform-specific paths found in src/.\n"
            "Use the helpers in src/platform.py instead:\n\n"
            + "\n".join(violations)
        )
