"""FeedCursor advances one lazy listing in steps: no re-read, cancellable, typed errors."""

import pytest
import yt_dlp

from src import ytdlp
from src.errors import RateLimited
from src.feed_cursor import FeedCursor

FEED = [{"id": f"vid{n:08d}", "title": f"Video {n}"} for n in range(50)]


class _FakeYDL:
    """Records how the listing is opened and how far it was read."""

    opened: list[dict] = []
    reads = 0
    fail_at: int | None = None
    exits = 0
    sticky = False

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        _FakeYDL.exits += 1
        return False

    def extract_info(self, url, download=False):
        _FakeYDL.opened.append(self.opts)
        return {"entries": self._rows()}

    def _rows(self):
        for n, row in enumerate(FEED):
            if _FakeYDL.fail_at == n:
                _FakeYDL.fail_at = _FakeYDL.fail_at if _FakeYDL.sticky else None
                raise yt_dlp.utils.DownloadError("HTTP Error 429: Too Many Requests")
            _FakeYDL.reads += 1
            yield dict(row)


@pytest.fixture
def fake_ydl(monkeypatch):
    _FakeYDL.opened, _FakeYDL.reads, _FakeYDL.fail_at, _FakeYDL.exits = [], 0, None, 0
    _FakeYDL.sticky = False
    monkeypatch.setattr(ytdlp, "_make_ydl", lambda opts, config, auth=False: _FakeYDL(opts))
    monkeypatch.setattr("src.feed_cursor.time.sleep", lambda s: None)
    return _FakeYDL


def test_batches_continue_without_rereading_the_top(fake_ydl, temp_cache):
    cur = FeedCursor("u", None, temp_cache)
    first = cur.take(20, set())
    second = cur.take(20, set())
    assert [e["id"] for e in first + second] == [e["id"] for e in FEED[:40]]
    assert len(fake_ydl.opened) == 1
    assert fake_ydl.reads == 40


def test_skipped_ids_are_consumed_but_not_returned(fake_ydl, temp_cache):
    cur = FeedCursor("u", None, temp_cache)
    got = cur.take(10, {e["id"] for e in FEED[:5]})
    assert [e["id"] for e in got] == [e["id"] for e in FEED[5:15]]


def test_exhausted_feed_stops_asking(fake_ydl, temp_cache):
    cur = FeedCursor("u", None, temp_cache)
    assert len(cur.take(80, set())) == 50
    assert cur.exhausted
    assert cur.take(80, set()) == []
    assert len(fake_ydl.opened) == 1


def test_close_during_a_take_stops_it_and_closes_the_extractor_once(fake_ydl, temp_cache):
    cur = FeedCursor("u", None, temp_cache)
    got = cur.take(30, set(), on_first_batch=lambda rows: cur.close(), first_batch_size=5)
    assert len(got) == 5
    assert cur.closed and fake_ydl.exits == 1
    assert cur.take(10, set()) == []


def test_cancel_all_stops_the_cursor(fake_ydl, temp_cache):
    cur = FeedCursor("u", None, temp_cache)
    cur.take(5, set())
    ytdlp.cancel_all()
    assert cur.closed and cur.take(5, set()) == []


def test_a_failure_before_any_row_raises_a_typed_error(fake_ydl, temp_cache):
    fake_ydl.fail_at, fake_ydl.sticky = 0, True
    cur = FeedCursor("u", None, temp_cache)
    with pytest.raises(RateLimited):
        cur.take(5, set())


def test_a_failure_after_rows_keeps_them_and_the_next_take_reopens(fake_ydl, temp_cache):
    fake_ydl.fail_at = 7
    cur = FeedCursor("u", None, temp_cache)
    got = cur.take(20, set())
    assert len(got) == 7
    again = cur.take(20, {e["id"] for e in got})
    assert [e["id"] for e in again][:3] == [e["id"] for e in FEED[7:10]]
    assert len(fake_ydl.opened) == 2


MIXED = [
    {"id": "vid00000001", "title": "A video"},
    {"id": "RDdQw4w9WgXcQ", "ie_key": "YoutubeTab", "url": "https://www.youtube.com/playlist?list=RDdQw4w9WgXcQ",
     "title": "Mix - Rick", "channel": "YouTube", "thumbnails": [{"url": "https://i.ytimg.com/vi/x/hq.jpg"}]},
    {"id": "UCabc", "ie_key": "YoutubeTab", "url": "https://www.youtube.com/channel/UCabc", "title": "A channel"},
    {"id": "PLhits", "ie_key": "YoutubeTab", "url": "https://www.youtube.com/playlist?list=PLhits", "title": "Hits"},
]


def test_home_keeps_playlist_and_mix_rows_and_the_other_feeds_do_not(fake_ydl, temp_cache, monkeypatch):
    monkeypatch.setattr(_FakeYDL, "_rows", lambda self: iter([dict(r) for r in MIXED]))
    home = FeedCursor("u", None, temp_cache, playlists=True).take(10, set())
    assert [e["id"] for e in home] == ["vid00000001", "RDdQw4w9WgXcQ", "PLhits"]
    mix = home[1]
    assert mix["_is_playlist"] and mix["url"].endswith("list=RDdQw4w9WgXcQ") and mix["_playlist_name"] == "Mix - Rick"
    assert mix["thumbnail"] == "https://i.ytimg.com/vi/x/hq.jpg"
    other = FeedCursor("u", None, temp_cache).take(10, set())
    assert [e["id"] for e in other] == ["vid00000001"]
