"""Search sort and type: params blobs, mixed result rows, the cache per sort/type, results beyond the first 50."""

import base64
import json
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pytest

import src.ytdlp as ytdlp
from src import feed_cache, innertube
from src.search_stack import SearchStack

FIXTURES = Path(__file__).parent.parent / "fixtures"


def mixed() -> dict:
    return json.loads((FIXTURES / "innertube_search_mixed.json").read_text(encoding="utf-8"))


def test_params_blobs_are_the_documented_single_filters_and_their_combinations():
    assert innertube.search_params() == ""
    assert innertube.search_params("date") == "CAI="
    assert innertube.search_params("views") == "CAM="
    assert innertube.search_params(kind="video") == "EgIQAQ=="
    assert innertube.search_params(kind="channel") == "EgIQAg=="
    assert innertube.search_params(kind="playlist") == "EgIQAw=="
    assert base64.b64decode(innertube.search_params("views", "playlist")) == bytes([8, 3, 0x12, 2, 0x10, 3])
    assert innertube.search_params("bogus", "bogus") == ""


def test_mixed_page_gives_video_channel_and_playlist_rows_and_skips_the_rest():
    with patch.object(innertube, "_post_json", return_value=mixed()):
        rows = innertube.search("lofi", count=10)
    kinds = ["channel" if r.get("_is_channel") else "playlist" if r.get("_is_playlist") else "video" for r in rows]
    assert kinds == ["video", "channel", "playlist", "playlist"]
    channel = rows[1]
    assert channel["id"] == "UCchannel0000000000000001" and channel["channel_url"].endswith("/@LofiGirl")
    assert channel["subscriber_count"] == 13_400_000 and channel["thumbnail"].startswith("https://yt3.ggpht.com")
    assert channel["description"] == "Music to study to"
    playlist = rows[2]
    assert playlist["_playlist_name"] == "Lofi mix" and playlist["playlist_count"] == 250
    assert playlist["url"].endswith("list=PLplaylist00000000000000000000001") and playlist["uploader"] == "Lofi Girl"
    assert rows[3]["title"] == "Lockup list"


def _mixed_page(url, payload, **_):
    return mixed()


def _search_rows(seen, query, **kw):
    seen.append((kw["sort"], kw["kind"]))
    return _rows(10)


def test_params_go_with_the_first_request_only():
    with patch.object(innertube, "_post_json", side_effect=_mixed_page) as post:
        innertube.search("x", count=100, sort="date", kind="video")
    calls = [c.args[1] for c in post.call_args_list]
    assert calls[0]["params"] == "CAISAhAB" and "params" not in calls[1] and "continuation" in calls[1]


def test_default_search_sends_no_params():
    seen = []
    with patch.object(innertube, "_post_json", side_effect=lambda u, p, **_: seen.append(p) or None):
        innertube.search("x")
    assert "params" not in seen[0]


def test_search_stack_filters_belong_to_the_search_and_reset_its_position():
    stack = SearchStack()
    stack.push("a")
    stack.save_position(3, "id1")
    stack.set_filter("sort", "date")
    assert (stack.sort, stack.kind, stack.take_position()) == ("date", "all", (1, None))
    stack.push("b")
    assert (stack.sort, stack.kind) == ("relevance", "all")
    stack.pop()
    assert stack.sort == "date" and "sorted by date" in stack.breadcrumb()
    stack.set_filter("kind", "channel")
    assert "channels only" in stack.breadcrumb()


def _rows(n, start=0):
    return [{"id": f"id{i:09d}", "title": f"t{i}"} for i in range(start, start + n)]


def test_each_sort_and_type_has_its_own_cache_entry(temp_cache):
    seen = []
    with patch.object(ytdlp.innertube, "search", side_effect=partial(_search_rows, seen)):
        ytdlp.fetch_search_batch("q", None, temp_cache)
        ytdlp.fetch_search_batch("q", None, temp_cache)
        ytdlp.fetch_search_batch("q", None, temp_cache, sort="date")
        ytdlp.fetch_search_batch("q", None, temp_cache, kind="channel")
        ytdlp.fetch_search_batch("q", None, temp_cache, sort="date")
    assert seen == [("relevance", "all"), ("date", "all"), ("relevance", "channel")]
    keys = {feed_cache.search_cache_key("q", s, k) for s in ("relevance", "date") for k in ("all", "channel")}
    assert len(keys) == 4


def test_extension_ids_join_the_cached_list_and_a_restore_reads_up_to_200(temp_cache):
    batches = iter([_rows(50), _rows(50, 50), _rows(50, 100), _rows(50, 150)])
    shown: set[str] = set()
    with patch.object(ytdlp.innertube, "search", side_effect=lambda *a, **k: next(batches)):
        for _ in range(4):
            got = ytdlp.fetch_search_batch("q", None, temp_cache, skip_ids=set(shown))
            shown |= {e["id"] for e in got}
    assert len(shown) == 200
    restored = ytdlp.fetch_search_batch("q", None, temp_cache)
    assert [e["id"] for e in restored] == [f"id{i:09d}" for i in range(200)]


def test_no_ytdlp_fallback_for_a_filtered_search(temp_cache, monkeypatch):
    monkeypatch.setattr(ytdlp.innertube, "search", lambda *a, **k: [])
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: pytest.fail("yt-dlp cannot filter"))
    assert ytdlp.fetch_search_batch("q", None, temp_cache, sort="date") == []
    assert ytdlp.fetch_search_batch("q", None, temp_cache, kind="channel") == []


def test_extension_without_a_cached_list_does_not_store_a_partial_one(temp_cache):
    with patch.object(ytdlp.innertube, "search", return_value=_rows(10, 50)):
        ytdlp.fetch_search_batch("q", None, temp_cache, skip_ids={f"id{i:09d}" for i in range(50)})
    assert temp_cache.get_feed(feed_cache.search_cache_key("q", "relevance", "all")) is None
