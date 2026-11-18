"""Persistent search history: dedupe, cap, removal, matching, the config switch."""

import json

from src import search_history
from src.config import Config


def test_newest_first_and_deduped_without_case(temp_search_history):
    for q in ("cats", "dogs", "CATS"):
        search_history.add(q)
    assert search_history.all_queries() == ["CATS", "dogs"]


def test_capped_at_one_hundred(temp_search_history):
    for i in range(130):
        search_history.add(f"q{i}")
    queries = search_history.all_queries()
    assert len(queries) == search_history.MAX_QUERIES and queries[0] == "q129"


def test_records_carry_a_timestamp_and_reach_disk(temp_search_history):
    search_history.add("cats")
    search_history._store.flush()
    raw = json.loads(temp_search_history.read_text(encoding="utf-8"))
    assert raw["data"][0]["q"] == "cats" and raw["data"][0]["at"] > 0


def test_remove_and_clear(temp_search_history):
    for q in ("a", "b", "c"):
        search_history.add(q)
    search_history.remove("B")
    assert search_history.all_queries() == ["c", "a"]
    search_history.clear()
    assert search_history.all_queries() == []


def test_prefix_matches_come_before_substring_matches(temp_search_history):
    for q in ("rust tutorial", "learn rust", "python", "rusty nail"):
        search_history.add(q)
    assert search_history.matching("rust") == ["rusty nail", "rust tutorial", "learn rust"]
    assert search_history.matching("") == ["rusty nail", "python", "learn rust", "rust tutorial"]


def test_switch_off_records_nothing(temp_search_history, tmp_path):
    config = Config(path=str(tmp_path / "c.yaml"))
    config.set("search_history", False)
    search_history.add("cats", config)
    assert search_history.all_queries() == []
    assert Config(path=str(tmp_path / "other.yaml")).search_history_enabled
