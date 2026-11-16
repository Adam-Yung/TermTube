import io
import urllib.error
from pathlib import Path

import pytest

from src import feeds, innertube

FIXTURE = Path(__file__).parent.parent / "fixtures" / "channel_feed.xml"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(feeds, "_rss_state", feeds._DeadFlag())


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO())


def test_parse_atom_reads_entries():
    entries = feeds.parse_atom(FIXTURE.read_bytes())
    assert [e["id"] for e in entries] == ["AAAAAAAAAAA", "BBBBBBBBBBB"]
    first = entries[0]
    assert first["title"] == "First upload" and first["upload_date"] == "20261110"
    assert first["channel"] == first["uploader"] == "Test Channel" and first["view_count"] == 12345
    assert first["thumbnail"].endswith("AAAAAAAAAAA/hqdefault.jpg")
    assert entries[1]["view_count"] is None


def test_parse_atom_survives_garbage():
    assert feeds.parse_atom(b"<html>not a feed") == []


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_rss_success_skips_innertube(monkeypatch):
    monkeypatch.setattr(feeds.urllib.request, "urlopen", lambda *a, **k: FakeResponse(FIXTURE.read_bytes()))
    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda *a, **k: pytest.fail("fallback must not run"))
    assert len(feeds.channel_latest("UCx")) == 2


def test_404_falls_back_to_innertube(monkeypatch):
    def raise404(*a, **k):
        raise http_error(404)

    monkeypatch.setattr(feeds.urllib.request, "urlopen", raise404)
    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda cid: [{"id": "fromInnerTube"}])
    assert feeds.channel_latest("UCx") == [{"id": "fromInnerTube"}]


def test_requests_carry_no_cookie_header(monkeypatch):
    seen = []

    def capture(req, **_):
        seen.append(req)
        return FakeResponse(FIXTURE.read_bytes())

    monkeypatch.setattr(feeds.urllib.request, "urlopen", capture)
    feeds.channel_latest("UCx")
    assert seen and not any(k.lower() in ("cookie", "authorization") for k in seen[0].headers)


def test_dead_flag_stops_rss_requests_until_expiry():
    now = [0.0]
    flag = feeds._DeadFlag(clock=lambda: now[0])
    flag.record(not_found=True)
    assert not flag.is_dead()
    flag.record(not_found=True)
    assert flag.is_dead()
    now[0] = feeds._DEAD_FOR_S - 1
    assert flag.is_dead()
    now[0] = feeds._DEAD_FOR_S
    assert not flag.is_dead()


def test_success_resets_the_404_count():
    flag = feeds._DeadFlag(clock=lambda: 0.0)
    flag.record(not_found=True)
    flag.record(not_found=False)
    flag.record(not_found=True)
    assert not flag.is_dead()


def test_dead_rss_costs_one_request_per_channel_after_threshold(monkeypatch):
    calls = []

    def raise404(*a, **k):
        calls.append(1)
        raise http_error(404)

    monkeypatch.setattr(feeds.urllib.request, "urlopen", raise404)
    monkeypatch.setattr(innertube, "fetch_channel_videos", lambda cid: [])
    for _ in range(5):
        feeds.channel_latest("UCx")
    assert len(calls) == feeds._DEAD_AFTER_404S
