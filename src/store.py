"""Locked, atomic, versioned JSON store shared by history, playlists and the other small user files."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import threading
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src import logger
from src.plat import atomic_write

_FLUSH_DELAY = 0.5
_pending: weakref.WeakSet[JsonStore] = weakref.WeakSet()


def flush_all() -> None:
    """Write every store that has deferred changes. Registered with atexit."""
    for store in list(_pending):
        store.flush()


atexit.register(flush_all)


class JsonStore:
    """One JSON file: `{"version": n, "data": ...}`, cached in memory, every access under one lock.

    `path` may be a callable so tests and Windows migration can move the file. A file without the envelope
    reads as version 1 (what history and playlists wrote before this class existed).
    """

    def __init__(
        self,
        path: Path | Callable[[], Path],
        version: int,
        default: Callable[[], Any],
        migrate: Callable[[Any, int], Any] | None = None,
    ) -> None:
        self._path_src = path
        self._version = version
        self._default = default
        self._migrate = migrate
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._data: Any = None
        self._loaded_from: Path | None = None
        self._dirty = False
        self._timer: threading.Timer | None = None

    @property
    def path(self) -> Path:
        return self._path_src() if callable(self._path_src) else self._path_src

    def read(self, fn: Callable[[Any], Any]) -> Any:
        """Run `fn(data)` under the lock and return its result. `fn` must not keep or mutate `data`."""
        with self._lock:
            return fn(self._ensure_loaded())

    def update(self, fn: Callable[[Any], Any], *, defer: bool = False) -> Any:
        """Run `fn(data)` under the lock; it mutates `data` in place and returns a result.

        A truthy result means "changed": the file is rewritten, now (an OSError propagates) or, with `defer`,
        by a background timer shortly after. The result is returned.
        """
        with self._lock:
            result = fn(self._ensure_loaded())
            if not result:
                return result
            self._dirty = True
            if defer:
                self._schedule()
                return result
        self.flush(raise_errors=True)
        return result

    def flush(self, *, raise_errors: bool = False) -> None:
        """Write pending changes now."""
        with self._write_lock:
            with self._lock:
                if not self._dirty:
                    return
                path = self.path
                payload = json.dumps(
                    {"version": self._version, "data": self._data}, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self._dirty = False
                self._timer = None
                _pending.discard(self)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(path, payload)
            except OSError as exc:
                with self._lock:
                    self._dirty = True
                logger.warning("%s not saved: %s", path.name, exc)
                if raise_errors:
                    raise

    def _schedule(self) -> None:
        _pending.add(self)
        if self._timer is None:
            self._timer = threading.Timer(_FLUSH_DELAY, self.flush)
            self._timer.daemon = True
            self._timer.start()

    def _ensure_loaded(self) -> Any:
        path = self.path
        if self._data is not None and self._loaded_from == path:
            return self._data
        self._data = self._load(path)
        self._loaded_from = path
        return self._data

    def _load(self, path: Path) -> Any:
        if not path.exists():
            return self._default()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._keep_bad_copy(path, "not valid JSON")
            return self._default()
        except OSError as exc:
            logger.warning("%s unreadable: %s", path.name, exc)
            return self._default()
        if isinstance(raw, dict) and isinstance(raw.get("version"), int) and "data" in raw:
            version, data = raw["version"], raw["data"]
        else:
            version, data = 1, raw
        if version > self._version:
            self._keep_bad_copy(path, f"version {version} is newer than {self._version}")
            return self._default()
        migrated = version < self._version
        try:
            if migrated and self._migrate:
                data = self._migrate(data, version)
        except Exception as exc:  # a migration bug must not lose the user's file
            self._keep_bad_copy(path, f"migration failed: {exc}")
            return self._default()
        if not isinstance(data, type(self._default())):
            self._keep_bad_copy(path, "unexpected shape")
            return self._default()
        if migrated:
            self._data, self._dirty = data, True
            self._schedule()
        return data

    @staticmethod
    def _keep_bad_copy(path: Path, why: str) -> None:
        bad = path.with_name(path.name + ".bad")
        logger.warning("%s ignored (%s); kept as %s", path.name, why, bad.name)
        try:
            shutil.copy2(path, bad)
            os.chmod(bad, 0o600)
        except OSError:
            pass
