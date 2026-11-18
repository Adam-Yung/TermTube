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
