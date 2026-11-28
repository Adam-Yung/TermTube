"""Tests for src/store.py: JsonStore."""

import json
import sys
import threading
from functools import partial
from unittest.mock import MagicMock

from src import store as store_mod
from src.store import JsonStore
from src.tests.fakes import run_in_threads


def make(path, version=1, migrate=None, default=dict):
    return JsonStore(path, version=version, default=default, migrate=migrate)


def test_missing_file_reads_as_default(tmp_path):
    assert make(tmp_path / "a.json").read(dict) == {}


def test_update_writes_envelope_privately(tmp_path):
    s = make(tmp_path / "a.json")
    assert s.update(lambda d: d.update(x=1) or True)
    raw = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert raw == {"version": 1, "data": {"x": 1}}
    if sys.platform != "win32":  # Windows has no POSIX modes
        assert (tmp_path / "a.json").stat().st_mode & 0o777 == 0o600


def test_falsy_result_does_not_write(tmp_path):
    s = make(tmp_path / "a.json")
    assert s.update(lambda d: False) is False
    assert not (tmp_path / "a.json").exists()


def test_legacy_file_without_envelope_reads_as_version_one(tmp_path):
    (tmp_path / "a.json").write_text('{"P": ["a"]}', encoding="utf-8")
    assert make(tmp_path / "a.json").read(dict) == {"P": ["a"]}


def test_corrupt_file_is_kept_as_bad_copy(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("{not json", encoding="utf-8")
    s = make(p)
    assert s.read(dict) == {}
    assert (tmp_path / "a.json.bad").read_text(encoding="utf-8") == "{not json"


def test_wrong_shape_is_kept_as_bad_copy(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert make(p).read(dict) == {}
    assert (tmp_path / "a.json.bad").exists()


def test_newer_version_is_not_overwritten_silently(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"version": 9, "data": {"x": 1}}', encoding="utf-8")
    assert make(p).read(dict) == {}
    assert json.loads((tmp_path / "a.json.bad").read_text(encoding="utf-8"))["version"] == 9


def _bump(calls, data, from_version):
    """A migration that adds one and records the version it started from."""
    calls.append(from_version)
    return {"n": data["n"] + 1}


def _append_25(store, n):
    for i in range(25):
        store.update(lambda d: d.append((n, i)) or True)


class _HeldFile:
    """An ``atomic_write`` that fails while another process "holds" the file."""

    held = True

    def __call__(self, path, payload):
        if self.held:
            raise PermissionError(13, "held")
        path.write_bytes(payload)


def test_migration_runs_once_and_is_persisted(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"version": 1, "data": {"n": 1}}', encoding="utf-8")
    calls = []

    migrate = partial(_bump, calls)
    s = make(p, version=2, migrate=migrate)
    assert s.read(dict) == {"n": 2}
    s.flush()
    assert json.loads(p.read_text(encoding="utf-8")) == {"version": 2, "data": {"n": 2}}
    assert make(p, version=2, migrate=migrate).read(dict) == {"n": 2}
    assert calls == [1]


def test_failing_migration_keeps_the_file(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"version": 1, "data": {}}', encoding="utf-8")

    assert make(p, version=2, migrate=MagicMock(side_effect=ValueError("x"))).read(dict) == {}
    assert (tmp_path / "a.json.bad").exists()


def test_path_can_move_between_calls(tmp_path):
    box = {"p": tmp_path / "one.json"}
    s = make(lambda: box["p"])
    s.update(lambda d: d.update(x=1) or True)
    box["p"] = tmp_path / "two.json"
    assert s.read(dict) == {}


def test_concurrent_updates_lose_nothing(tmp_path):
    s = make(tmp_path / "a.json", default=list)

    run_in_threads(partial(_append_25, s), 8)
    assert len(s.read(list)) == 200
    assert len(json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["data"]) == 200


def test_deferred_update_is_in_memory_at_once_and_flushed_later(tmp_path):
    p = tmp_path / "a.json"
    s = make(p, default=list)
    s.update(lambda d: d.append(1) or True, defer=True)
    assert s.read(list) == [1]
    assert not p.exists()
    store_mod.flush_all()
    assert json.loads(p.read_text(encoding="utf-8"))["data"] == [1]


def test_deferred_write_happens_by_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "_FLUSH_DELAY", 0.01)
    p = tmp_path / "a.json"
    s = make(p, default=list)
    s.update(lambda d: d.append(1) or True, defer=True)
    for _ in range(100):
        if p.exists():
            break
        threading.Event().wait(0.02)
    assert p.exists()


def test_failed_sync_write_does_not_raise_tells_once_and_retries_later(tmp_path, monkeypatch):
    s = make(tmp_path / "a.json")
    told = []
    store_mod.set_failure_hook(told.append)
    try:
        write = _HeldFile()
        monkeypatch.setattr(store_mod, "atomic_write", write)
        assert s.update(lambda d: d.update(x=1) or True)
        s.update(lambda d: d.update(y=2) or True)
        assert s.read(dict) == {"x": 1, "y": 2} and len(told) == 1 and "a.json" in told[0]
        write.held = False
        store_mod.flush_all()
        assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["data"] == {"x": 1, "y": 2}
        write.held = True
        s.update(lambda d: d.update(z=3) or True)
        s.update(lambda d: d.update(v=5) or True)
        assert len(told) == 2
    finally:
        store_mod.set_failure_hook(None)


def test_failed_deferred_write_does_not_raise(tmp_path, monkeypatch):
    s = make(tmp_path / "a.json")
    monkeypatch.setattr(store_mod, "atomic_write", lambda *a: (_ for _ in ()).throw(PermissionError("held")))
    s.update(lambda d: d.update(x=1) or True, defer=True)
    s.flush()
    assert s.read(dict) == {"x": 1}
