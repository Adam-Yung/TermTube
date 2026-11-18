"""The extraction window must cover the ids that get skipped, or a second batch comes back empty."""

import pytest

from src import ytdlp

_FEED = [{"id": f"vid{n:08d}", "title": f"Video {n}"} for n in range(60)]


class _FakeYDL:
    """Mimics yt-dlp's flat extraction: only the first ``playlistend`` rows exist."""

    seen_opts: list[dict] = []
    seen_urls: list[str] = []

    def __init__(self, opts):
        self.opts = opts
        _FakeYDL.seen_opts.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        _FakeYDL.seen_urls.append(url)
        return {"entries": [dict(e) for e in _FEED[: self.opts["playlistend"]]]}


@pytest.fixture
def fake_ydl(monkeypatch):
    _FakeYDL.seen_opts, _FakeYDL.seen_urls = [], []
    monkeypatch.setattr(ytdlp, "_make_ydl", lambda opts, config, auth=False: _FakeYDL(opts))
    return _FakeYDL


def test_second_batch_yields_new_items(fake_ydl, temp_cache):
    first = ytdlp.fetch_page_batch("https://www.youtube.com/", None, temp_cache, count=20)
    seen = {e["id"] for e in first}
    second = ytdlp.fetch_page_batch("https://www.youtube.com/", None, temp_cache, count=20, skip_ids=seen)

    assert len(first) == 20
    assert len(second) == 20
    assert not seen & {e["id"] for e in second}
    assert [o["playlistend"] for o in fake_ydl.seen_opts] == [20, 40]


def test_search_fallback_window_covers_skipped(fake_ydl, temp_cache, monkeypatch):
    monkeypatch.setattr(ytdlp.innertube, "search", lambda *a, **k: [])
    skip = {e["id"] for e in _FEED[:20]}
    results = ytdlp.fetch_search_batch("q", None, temp_cache, count=20, skip_ids=skip)

    assert len(results) == 20
    assert fake_ydl.seen_urls == ["ytsearch40:q"]


def test_account_feed_tolerates_malformed_flat_entries():
    """Fields of a real `:ythis` entry are unverified offline: keep what is there, skip non-videos, never raise."""
    from unittest.mock import MagicMock, patch

    import src.ytdlp as ytdlp

    rows = [
        None, "text", 7, {}, {"id": 5}, {"id": "short"}, {"id": "abcdefghijk", "_type": "playlist"},
        {"id": "abcdefghijl"},
        {"id": "abcdefghijm", "title": "Full", "uploader": "Chan", "duration": 61.0, "channel": "Chan"},
    ]
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = {"entries": rows}
    cache = MagicMock()
    with patch("src.ytdlp._make_ydl", return_value=ydl) as make:
        out = ytdlp.fetch_page_batch(ytdlp.FEED_URLS["yt_history"], MagicMock(), cache, count=10, auth=True)
    assert [e["id"] for e in out] == ["abcdefghijl", "abcdefghijm"]
    assert make.call_args.kwargs["auth"] is True
    assert ydl.extract_info.call_args.args[0] == "https://www.youtube.com/feed/history"
