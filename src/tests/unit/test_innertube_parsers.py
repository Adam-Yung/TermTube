import pytest
import json
from pathlib import Path
from unittest.mock import patch

from src import innertube

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_search_parses_videos_and_skips_non_videos():
    page = load("innertube_search.json")
    with patch.object(innertube, "_post_json", return_value=page):
        results = innertube.search_videos("lofi", count=3)
    assert len(results) == 3
    first = results[0]
    assert len(first["id"]) == 11 and first["title"] and first["channel_id"].startswith("UC")
    assert first["channel_url"].endswith(first["channel_id"])
    assert isinstance(first["duration"], int) or first["duration"] is None


def test_search_follows_continuation_until_count():
    page = load("innertube_search.json")
    calls = []

    def fake(url, payload, **_):
        calls.append(payload)
        return page if "query" in payload else {
            "onResponseReceivedCommands": [{"appendContinuationItemsAction": {"continuationItems": [
                {"itemSectionRenderer": {"contents": [
                    {"videoRenderer": {"videoId": "AAAAAAAAAAA", "title": {"simpleText": "next"}}}]}}]}}]}

    with patch.object(innertube, "_post_json", side_effect=fake):
        results = innertube.search_videos("lofi", count=4)
    assert [r["id"] for r in results][-1] == "AAAAAAAAAAA"
    assert "continuation" in calls[1] and "query" not in calls[1]


def test_search_skips_given_ids_and_survives_failure():
    page = load("innertube_search.json")
    with patch.object(innertube, "_post_json", return_value=page):
        everything = innertube.search_videos("x", count=10)
        skipped = innertube.search_videos("x", count=10, skip_ids={everything[0]["id"]})
    assert everything[0]["id"] not in [r["id"] for r in skipped]
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.search_videos("x") == []


def test_channel_info_from_channel_url_needs_no_resolve_call():
    browse = load("innertube_channel.json")
    url = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
    with patch.object(innertube, "_post_json", return_value=browse) as post:
        info = innertube.fetch_channel_info(url)
    assert post.call_count == 1
    assert info["channel"] == "Rick Astley" and info["subscriber_count"] == 4_560_000
    assert info["channel_id"] == "UCuAXFkgsw1L7xaCfnd5JJOw" and info["thumbnail"].startswith("https://")
    assert info["uploader_url"] == "https://www.youtube.com/@RickAstleyYT"


def test_channel_info_resolves_handle_first():
    responses = [load("innertube_resolve.json"), load("innertube_channel.json")]
    with patch.object(innertube, "_post_json", side_effect=responses):
        info = innertube.fetch_channel_info("https://www.youtube.com/@RickAstleyYT")
    assert info["channel_id"].startswith("UC")


def test_channel_info_none_when_unresolvable():
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.fetch_channel_info("https://www.youtube.com/@nobody") is None


def test_ytdlp_search_uses_innertube_then_falls_back(tmp_path, monkeypatch):
    import src.ytdlp as ytdlp
    from unittest.mock import MagicMock

    cache = MagicMock()
    cache.get_feed.return_value = None
    cache.is_feed_fresh.return_value = False
    hit = [{"id": f"{i:011d}", "title": "t"} for i in range(3)]
    monkeypatch.setattr(ytdlp.innertube, "search_videos", lambda *a, **k: hit)
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: pytest.fail("yt-dlp must not run"))
    assert ytdlp.fetch_search_batch("q", None, cache, count=3) == hit

    fallback = [{"id": "fallbackvid", "title": "f"}]
    monkeypatch.setattr(ytdlp.innertube, "search_videos", lambda *a, **k: [])
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: (fallback, ["fallbackvid"]))
    assert ytdlp.fetch_search_batch("q2", None, cache, count=3) == fallback


def test_search_reports_first_page_before_fetching_more():
    page = load("innertube_search.json")
    order = []

    def fake(url, payload, **_):
        order.append("post")
        return page if "query" in payload else None

    with patch.object(innertube, "_post_json", side_effect=fake):
        innertube.search_videos("x", count=50, on_first_batch=lambda e: order.append(f"first:{len(e)}"))
    assert order == ["post", "first:3", "post"]
