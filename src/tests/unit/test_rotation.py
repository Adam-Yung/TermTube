"""Nothing grows without bound: caches are pruned by age and count, the debug log rotates, history stays capped."""

import os
import time

import pytest

from src import history, logger, sponsorblock, store
from src.config import Config


@pytest.fixture
def cfg(tmp_path):
    return Config(path=str(tmp_path / "config.yaml"))


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_search_feeds_expire_and_are_capped(temp_cache, tmp_path, monkeypatch):
    monkeypatch.setattr("src.cache.CACHE_DIR", tmp_path)
    for i in range(60):
        (tmp_path / f"feed_search_{i:02d}.json").write_text("[]", encoding="utf-8")
    (tmp_path / "feed_home.json").write_text("[]", encoding="utf-8")
    stale = tmp_path / "feed_search_stale.json"
    stale.write_text("[]", encoding="utf-8")
    _age(stale, 30)
    temp_cache.prune_old_searches()
    left = sorted(p.name for p in tmp_path.glob("feed_search_*.json"))
    assert len(left) == 50 and "feed_search_stale.json" not in left
    assert (tmp_path / "feed_home.json").exists()


def test_sponsorblock_cache_drops_expired_and_caps(tmp_path, monkeypatch):
    monkeypatch.setattr("src.sponsorblock._CACHE_DIR", tmp_path)
    old = tmp_path / "old.json"
    old.write_text("[]", encoding="utf-8")
    _age(old, 2)
    for i in range(5):
        (tmp_path / f"v{i}.json").write_text("[]", encoding="utf-8")
    sponsorblock.prune_cache(max_count=3)
    assert len(list(tmp_path.glob("*.json"))) == 3 and not old.exists()


def test_debug_log_rotates_at_the_size_cap_and_old_logs_go(tmp_path, monkeypatch):
    monkeypatch.setattr("src.logger._LOG_DIR", tmp_path)
    monkeypatch.setattr("src.logger.MAX_LOG_BYTES", 2000)
    for i in range(logger.KEEP_LOG_FILES + 3):
        (tmp_path / f"2020010{i}_000000.log").write_text("x", encoding="utf-8")
    stale = tmp_path / "ancient.log"
    stale.write_text("x", encoding="utf-8")
    _age(stale, 30)
    logger.setup(debug=True)
    try:
        for i in range(200):
            logger.info("line %d %s", i, "y" * 50)
        current = logger.log_file()
        assert current.stat().st_size <= 2000 + 200
        assert current.with_name(current.name + ".1").exists()
        assert not current.with_name(current.name + ".2").exists()
    finally:
        logger.setup(debug=False)
    assert not stale.exists()
    assert len(list(tmp_path.glob("*.log*"))) <= logger.KEEP_LOG_FILES + 2


def test_history_file_stays_bounded_at_the_largest_cap(temp_history, cfg):
    cfg.set("history_max", 5000)
    for i in range(5200):
        history.add({"id": f"v{i}", "title": "t" * 200, "description": "d" * 5000}, cfg)
    store.flush_all()
    assert len(history.all_entries()) == 5000
    assert temp_history.stat().st_size < 3 * 1024 * 1024
