import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src import innertube

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


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
    from unittest.mock import MagicMock

    import src.ytdlp as ytdlp

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


def test_channel_playlists_parse_fixture_and_follow_continuation():
    first, more = load("innertube_playlists.json"), load("innertube_playlists_more.json")
    calls = []

    def fake(url, payload, **_):
        calls.append(payload)
        return first if "browseId" in payload else more

    with patch.object(innertube, "_post_json", side_effect=fake):
        entries = innertube.fetch_channel_playlists("UC_x5XG1OV2P6uZZ5FSM9Ttw")
    assert len(entries) == 5 and "continuation" in calls[1] and "browseId" not in calls[1]
    pl = entries[0]
    assert pl["id"].startswith("PL") and pl["title"] == "Building with Gemini"
    assert pl["url"] == f"https://www.youtube.com/playlist?list={pl['id']}" == pl["webpage_url"]
    assert pl["playlist_count"] == 11 and pl["thumbnail"].startswith("https://")
    assert pl["_is_playlist"] and pl["_playlist_name"] == pl["title"]


def test_channel_playlists_respect_count_and_survive_failure():
    first = load("innertube_playlists.json")
    with patch.object(innertube, "_post_json", return_value=first) as post:
        assert len(innertube.fetch_channel_playlists("UCx", count=2)) == 2
    assert post.call_count == 1
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.fetch_channel_playlists("UCx") == []


def test_channel_screen_playlists_fall_back_to_ytdlp(monkeypatch):
    from types import SimpleNamespace

    import src.ytdlp as ytdlp
    from src.tui.screens.channel_screen import ChannelScreen

    host = SimpleNamespace(_channel_id=lambda: "UCx", _channel_url="u", app=SimpleNamespace(config=None, cache=None))
    monkeypatch.setattr(innertube, "fetch_channel_playlists", lambda cid: [{"id": "PLa"}])
    monkeypatch.setattr(ytdlp, "fetch_channel_playlists", lambda *a, **k: pytest.fail("yt-dlp must not run"))
    assert ChannelScreen._fetch_playlists(host) == [{"id": "PLa"}]

    monkeypatch.setattr(innertube, "fetch_channel_playlists", lambda cid: [])
    monkeypatch.setattr(ytdlp, "fetch_channel_playlists", lambda *a, **k: [{"id": "PLb"}])
    assert ChannelScreen._fetch_playlists(host) == [{"id": "PLb"}]


class _FakeConn:
    """Scripted stand-in for HTTPSConnection; ``script`` items are an Exception to raise or (status, body)."""
    instances: list = []

    def __init__(self, host, timeout=None, script=None):
        self.host, self.timeout, self.sock, self.requests = host, timeout, None, []
        self.script = _FakeConn.script
        self.closed = False
        _FakeConn.instances.append(self)

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, headers))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        self._item = item

    def getresponse(self):
        status, body = self._item
        return type("R", (), {"status": status, "read": lambda s: body})()

    def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    _FakeConn.instances, _FakeConn.script = [], []
    monkeypatch.setattr(innertube.http.client, "HTTPSConnection", _FakeConn)
    monkeypatch.setattr(innertube, "_local", __import__("threading").local())
    return _FakeConn


def test_post_reuses_the_connection_and_sends_path_with_query(transport):
    transport.script[:] = [(200, b'{"a": 1}'), (200, b'{"a": 2}')]
    assert innertube._post_json(innertube._BROWSE_URL, {}) == {"a": 1}
    assert innertube._post_json(innertube._BROWSE_URL, {}) == {"a": 2}
    assert len(transport.instances) == 1
    assert transport.instances[0].requests[0][1] == "/youtubei/v1/browse?prettyPrint=false"
    assert transport.instances[0].host == "www.youtube.com"


def test_post_retries_once_on_a_stale_reused_connection(transport):
    transport.script[:] = [(200, b"{}"), ConnectionResetError("closed"), (200, b'{"ok": true}')]
    innertube._post_json(innertube._BROWSE_URL, {})
    assert innertube._post_json(innertube._BROWSE_URL, {}) == {"ok": True}
    assert len(transport.instances) == 2 and transport.instances[0].closed


def test_post_gives_up_after_one_fresh_failure_and_on_http_errors(transport):
    transport.script[:] = [ConnectionResetError("down")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None
    assert len(transport.instances) == 1
    transport.script[:] = [(500, b"oops")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None
    transport.script[:] = [(200, b"not json")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None


def test_post_connections_are_per_thread(transport):
    import threading

    transport.script[:] = [(200, b"{}"), (200, b"{}")]
    innertube._post_json(innertube._BROWSE_URL, {})
    worker = threading.Thread(target=lambda: innertube._post_json(innertube._BROWSE_URL, {}))
    worker.start()
    worker.join()
    assert len(transport.instances) == 2


def test_post_sends_no_cookie_header(transport):
    transport.script[:] = [(200, b"{}")]
    innertube._post_json(innertube._BROWSE_URL, {})
    assert not any(k.lower() in ("cookie", "authorization") for k in transport.instances[0].requests[0][2])


def test_channel_screen_videos_use_innertube_then_ytdlp(monkeypatch):
    from types import SimpleNamespace

    import src.ytdlp as ytdlp
    from src.tui.screens.channel_screen import ChannelScreen

    host = SimpleNamespace(
        _channel_id=lambda: "UCx", _channel_url="u", _channel_name="Chan", app=SimpleNamespace(config=None, cache=None)
    )
    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda cid: [{"id": "AAAAAAAAAAA"}])
    monkeypatch.setattr(ytdlp, "fetch_channel_videos", lambda *a, **k: pytest.fail("yt-dlp must not run"))
    rows = ChannelScreen._fetch_videos(host, "date")
    assert rows == [{"id": "AAAAAAAAAAA", "channel": "Chan", "uploader": "Chan"}]

    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda cid: [])
    monkeypatch.setattr(ytdlp, "fetch_channel_videos", lambda *a, **k: [{"id": "fallbackvid"}])
    assert ChannelScreen._fetch_videos(host, "date") == [{"id": "fallbackvid"}]
    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda cid: pytest.fail("other sorts use yt-dlp"))
    assert ChannelScreen._fetch_videos(host, "views") == [{"id": "fallbackvid"}]
