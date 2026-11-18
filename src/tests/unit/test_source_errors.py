"""Typed source errors: classifier table, yt-dlp raising, and the InnerTube-to-yt-dlp fallback ladder."""

import pytest
import yt_dlp

from src import innertube, ytdlp
from src.errors import ExtractionFailed, NetworkDown, RateLimited, SignInRequired, classify


@pytest.mark.parametrize(
    "text, status, kind",
    [
        ("Sign in to confirm you're not a bot", None, SignInRequired),
        ("ERROR: login required", None, SignInRequired),
        ("HTTP Error 403: Forbidden", None, SignInRequired),
        ("whatever", 401, SignInRequired),
        ("HTTP Error 429: Too Many Requests", None, RateLimited),
        ("Too many requests", None, RateLimited),
        ("whatever", 429, RateLimited),
        ("<urlopen error [Errno 8] nodename nor servname provided>", None, NetworkDown),
        ("Unable to download webpage: timed out", None, NetworkDown),
        ("HTTP Error 503: Service Unavailable", None, NetworkDown),
        ("whatever", 502, NetworkDown),
        ("Unable to extract initial data", None, ExtractionFailed),
        ("Video unavailable", None, ExtractionFailed),
    ],
)
def test_classifier_table(text, status, kind):
    assert type(classify(Exception(text), status=status)) is kind


def test_classify_keeps_a_typed_error_and_reads_wrapped_oserrors():
    err = RateLimited("x")
    assert classify(err) is err
    assert isinstance(classify(ConnectionResetError("boom")), NetworkDown)


def test_every_error_has_a_user_message():
    for cls in (SignInRequired, RateLimited, NetworkDown, ExtractionFailed):
        assert cls("d").message and str(cls("d")) == "d"
        assert cls(retry_after=30).retry_after == 30


class _Ydl:
    def __init__(self, info=None, exc=None):
        self.info, self.exc = info, exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        if self.exc:
            raise self.exc
        return self.info


@pytest.fixture
def extract(monkeypatch):
    monkeypatch.setattr(ytdlp, "_RETRY_DELAY_S", 0)
    monkeypatch.setattr(ytdlp, "invalidate", lambda: calls.append("invalidate"))
    calls = []

    def run(ydl):
        monkeypatch.setattr(ytdlp, "_make_ydl", lambda *a, **k: ydl)
        return ytdlp._extract_videos("u", None, _Cache(), count=5, skip_ids=set(), auth=True)

    run.calls = calls
    return run


class _Cache:
    def put_video(self, entry):
        pass


@pytest.mark.parametrize(
    "text, kind",
    [("Sign in to confirm", SignInRequired), ("HTTP Error 429", RateLimited), ("urlopen error x", NetworkDown),
     ("Unable to extract", ExtractionFailed)],
)
def test_extract_raises_the_classified_error(extract, text, kind):
    with pytest.raises(kind):
        extract(_Ydl(exc=yt_dlp.utils.DownloadError(text)))


def test_sign_in_failure_invalidates_the_jar(extract):
    with pytest.raises(SignInRequired):
        extract(_Ydl(exc=yt_dlp.utils.DownloadError("Sign in")))
    assert "invalidate" in extract.calls


def test_an_honestly_empty_feed_is_an_empty_list(extract):
    assert extract(_Ydl(info={"entries": []})) == ([], [])


def test_search_falls_back_to_ytdlp_when_innertube_errors(monkeypatch):
    def boom(*a, **k):
        raise NetworkDown("x")

    monkeypatch.setattr(innertube, "search", boom)
    entry = {"id": "abcdefghij1", "title": "t"}
    monkeypatch.setattr(ytdlp, "_extract_videos", lambda *a, **k: ([entry], ["abcdefghij1"]))
    monkeypatch.setattr(ytdlp, "_cached_entries", lambda *a: None)
    monkeypatch.setattr(ytdlp, "_remember_search", lambda *a: None)
    assert ytdlp.fetch_search_batch("q", None, _Cache()) == [entry]


def test_filtered_search_does_not_fall_back_and_surfaces_the_error(monkeypatch):
    def boom(*a, **k):
        raise RateLimited("x")

    monkeypatch.setattr(innertube, "search", boom)
    monkeypatch.setattr(ytdlp, "_cached_entries", lambda *a: None)
    with pytest.raises(RateLimited):
        ytdlp.fetch_search_batch("q", None, _Cache(), sort="date")

