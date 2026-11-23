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
        results = innertube.search("lofi", count=3)
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
        results = innertube.search("lofi", count=4)
    assert [r["id"] for r in results][-1] == "AAAAAAAAAAA"
    assert "continuation" in calls[1] and "query" not in calls[1]


def test_search_skips_given_ids_and_survives_failure():
    page = load("innertube_search.json")
    with patch.object(innertube, "_post_json", return_value=page):
        everything = innertube.search("x", count=10)
        skipped = innertube.search("x", count=10, skip_ids={everything[0]["id"]})
    assert everything[0]["id"] not in [r["id"] for r in skipped]
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.search("x") == []


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
    monkeypatch.setattr(ytdlp.innertube, "search", lambda *a, **k: hit)
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: pytest.fail("yt-dlp must not run"))
    assert ytdlp.fetch_search_batch("q", None, cache, count=3) == hit

    fallback = [{"id": "fallbackvid", "title": "f"}]
    monkeypatch.setattr(ytdlp.innertube, "search", lambda *a, **k: [])
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: (fallback, ["fallbackvid"]))
    assert ytdlp.fetch_search_batch("q2", None, cache, count=3) == fallback


def test_search_reports_first_page_before_fetching_more():
    page = load("innertube_search.json")
    order = []

    def fake(url, payload, **_):
        order.append("post")
        return page if "query" in payload else None

    with patch.object(innertube, "_post_json", side_effect=fake):
        innertube.search("x", count=50, on_first_batch=lambda e: order.append(f"first:{len(e)}"))
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
def no_sleep(monkeypatch):
    pauses = []
    monkeypatch.setattr(innertube, "_sleep", pauses.append)
    return pauses


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(innertube, "_sleep", lambda s: None)


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


def test_post_gives_up_after_one_retry_and_on_http_errors(transport, no_sleep):
    transport.script[:] = [ConnectionResetError("down"), ConnectionResetError("down")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None
    assert len(transport.instances) == 2 and no_sleep == [innertube._RETRY_DELAY_S]
    transport.script[:] = [(404, b"gone")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None
    transport.script[:] = [(200, b"not json")]
    assert innertube._post_json(innertube._BROWSE_URL, {}) is None


def test_post_retries_a_429_or_5xx_once_after_a_pause(transport, no_sleep):
    transport.script[:] = [(429, b""), (200, b'{"ok": 1}')]
    assert innertube._post_json(innertube._BROWSE_URL, {}) == {"ok": 1}
    transport.script[:] = [(503, b""), (200, b'{"ok": 2}')]
    assert innertube._post_json(innertube._BROWSE_URL, {}) == {"ok": 2}
    assert no_sleep == [innertube._RETRY_DELAY_S] * 2


def test_strict_post_raises_a_typed_error_after_the_retry(transport, no_sleep):
    from src.errors import NetworkDown, RateLimited

    transport.script[:] = [(429, b""), (429, b"")]
    with pytest.raises(RateLimited):
        innertube._post_json(innertube._BROWSE_URL, {}, strict=True)
    transport.script[:] = [(502, b""), (500, b"")]
    with pytest.raises(NetworkDown):
        innertube._post_json(innertube._BROWSE_URL, {}, strict=True)
    transport.script[:] = [(404, b"")]
    assert innertube._post_json(innertube._BROWSE_URL, {}, strict=True) is None
    assert len(no_sleep) == 2


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
    host._label = lambda entries: ChannelScreen._label(host, entries)
    page_one = innertube.ChannelPage([{"id": "AAAAAAAAAAA"}], "T")
    monkeypatch.setattr(innertube, "fetch_channel_page", lambda cid, tab: page_one)
    monkeypatch.setattr(ytdlp, "fetch_channel_videos", lambda *a, **k: pytest.fail("yt-dlp must not run"))
    page = ChannelScreen._fetch_videos(host, "date")
    assert page.entries == [{"id": "AAAAAAAAAAA", "channel": "Chan", "uploader": "Chan"}] and page.token == "T"

    monkeypatch.setattr(innertube, "fetch_channel_page", lambda cid, tab: innertube.ChannelPage([]))
    monkeypatch.setattr(ytdlp, "fetch_channel_videos", lambda *a, **k: [{"id": "fallbackvid"}])
    assert ChannelScreen._fetch_videos(host, "date") == innertube.ChannelPage([{"id": "fallbackvid"}])
    monkeypatch.setattr(innertube, "fetch_channel_page", lambda *a: pytest.fail("other sorts use yt-dlp"))
    assert ChannelScreen._fetch_videos(host, "views").entries == [{"id": "fallbackvid"}]


def test_channel_videos_page_parses_rows_and_returns_the_continuation_token():
    with patch.object(innertube, "_post_json", return_value=load("innertube_channel_videos.json")) as post:
        page = innertube.fetch_channel_page("UCx", "videos")
    assert post.call_args.args[1]["params"] == innertube._CHANNEL_TAB_PARAMS["videos"]
    first, live = page.entries
    assert page.token == "TOKEN-PAGE-2"
    assert first["id"] == "AAAAAAAAAAA" and first["title"] == "First video" and first["duration"] == 225
    assert first["view_count"] == 1_200_000 and first["published_text"] == "2 days ago" and not first.get("is_live")
    assert live["is_live"] and live["view_count_text"] == "532 watching" and live["duration"] is None


def test_channel_continuation_page_sends_only_the_token_and_ends_without_one():
    with patch.object(innertube, "_post_json", return_value=load("innertube_channel_videos_more.json")) as post:
        page = innertube.fetch_channel_page("UCx", "videos", "TOKEN-PAGE-2")
    payload = post.call_args.args[1]
    assert payload["continuation"] == "TOKEN-PAGE-2" and "browseId" not in payload and "params" not in payload
    assert [e["id"] for e in page.entries] == ["CCCCCCCCCCC"] and page.token == ""


def test_channel_page_survives_failure_and_an_unexpected_shape():
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.fetch_channel_page("UCx") == innertube.ChannelPage([])
    with patch.object(innertube, "_post_json", return_value={"contents": []}):
        assert innertube.fetch_channel_page("UCx") == innertube.ChannelPage([])
    with patch.object(innertube, "_post_json", return_value={"onResponseReceivedActions": [{}]}):
        assert innertube.fetch_channel_page("UCx", token="t") == innertube.ChannelPage([])


def test_channel_shorts_page_reads_the_video_id_from_the_tap_or_the_entity_id():
    with patch.object(innertube, "_post_json", return_value=load("innertube_channel_shorts.json")) as post:
        page = innertube.fetch_channel_page("UCx", "shorts")
    assert post.call_args.args[1]["params"] == innertube._CHANNEL_TAB_PARAMS["shorts"]
    assert [e["id"] for e in page.entries] == ["SSSSSSSSSSS", "TTTTTTTTTTT"]
    short = page.entries[0]
    assert short["title"] == "A short" and short["view_count"] == 12_000 and short["thumbnail"].startswith("https://")
    assert short["webpage_url"].endswith("watch?v=SSSSSSSSSSS")


def test_channel_info_carries_video_count_join_date_and_the_tabs_the_channel_has():
    browse = load("innertube_channel.json")
    url = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
    with patch.object(innertube, "_post_json", return_value=browse):
        info = innertube.fetch_channel_info(url)
    assert info["video_count"] == 442 and info["joined"] == "" and info["tabs"] == []

    browse = {**browse, "contents": {"twoColumnBrowseResultsRenderer": {"tabs": [
        {"tabRenderer": {"title": title}} for title in ("Home", "Videos", "Live", "Playlists", "Community")]}}}
    browse["header"] = {"x": [{"text": "Joined Mar 3, 2011"}, {"content": "Joined Mar 3, 2011"}]}
    with patch.object(innertube, "_post_json", return_value=browse):
        info = innertube.fetch_channel_info(url)
    assert info["tabs"] == ["videos", "live", "playlists"]


def test_playlist_page_parses_videos_with_their_channel_and_returns_the_token():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos.json")) as post:
        page = innertube.fetch_playlist_page("PLabc")
    assert post.call_args.args[1]["browseId"] == "VLPLabc"
    first, second = page.entries
    assert page.token == "PL-TOKEN"
    assert first["id"] == "PPPPPPPPPPP" and first["title"] == "First track" and first["duration"] == 245
    assert first["uploader"] == "Other Channel" and first["channel_id"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert first["channel_url"].endswith(first["channel_id"]) and first["thumbnail"].endswith("hq.jpg")
    assert second["id"] == "QQQQQQQQQQQ" and "channel_id" not in second


def test_playlist_continuation_sends_only_the_token_and_failure_is_empty():
    more = load("innertube_channel_videos_more.json")
    with patch.object(innertube, "_post_json", return_value=more) as post:
        innertube.fetch_playlist_page("PLabc", "TOK")
    assert post.call_args.args[1]["continuation"] == "TOK" and "browseId" not in post.call_args.args[1]
    with patch.object(innertube, "_post_json", return_value=None):
        assert innertube.fetch_playlist_page("PLabc") == innertube.ChannelPage([])


def test_playlist_page_parses_the_lockup_layout_recorded_from_youtube():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos_lockup.json")):
        page = innertube.fetch_playlist_page("PLRPUpQa70I6A")
    first, second = page.entries
    assert first["id"] == "cv8tEbKtEvk" and first["title"].endswith("Gemini Live") and first["duration"] == 126
    assert first["uploader"] == "Google for Developers" and first["channel_id"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert second["id"] == "ID6vEy94j7c"
    assert page.token.startswith("4qmFsgIx")


def test_playlist_first_page_carries_the_header_recorded_from_youtube():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_page_header.json")):
        page = innertube.fetch_playlist_page("PLBTanuC8SLeZUH4mYXFvRbDfxTMKvNLHJ")
    info = page.info
    assert info["title"].startswith("Lofi Music 2027") and info["description"].startswith("Lofi Music 2027")
    assert (info["owner"], info["owner_id"]) == ("Hitsify", "UCnFrtWHPWzuvzMwwJLv9dnA")
    assert (info["video_count"], info["view_count"], info["updated"]) == (50, 62909, "Updated 4 days ago")
    assert info["thumbnail"].startswith("https://i.ytimg.com/vi/GgVcgbtHY9k/")
    assert info["playlist_id"] == "PLBTanuC8SLeZUH4mYXFvRbDfxTMKvNLHJ" and len(page.entries) == 2


def test_a_continuation_page_has_no_header():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_videos_lockup.json")):
        assert innertube.fetch_playlist_page("PLx", "tok").info is None


def test_an_unviewable_playlist_reports_youtubes_own_reason():
    with patch.object(innertube, "_post_json", return_value=load("innertube_playlist_unviewable.json")):
        page = innertube.fetch_playlist_page("RDdQw4w9WgXcQ")
    assert page.entries == []
    assert page.info == {"playlist_id": "RDdQw4w9WgXcQ", "unavailable": "This playlist type is unviewable."}
