"""release_download.github_latest_tag: the API first, the release page's redirect when the API is rate-limited."""

import io
import urllib.error
from functools import partial

import pytest

from src import release_download


class Reply(io.BytesIO):
    def __init__(self, body=b"", url=""):
        super().__init__(body)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def rate_limited(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 403, "rate limit exceeded", {}, io.BytesIO())


def test_the_api_answer_is_used_when_it_works(monkeypatch):
    reply = Reply(b'{"tag_name": "v1.2.3"}')
    monkeypatch.setattr(release_download.urllib.request, "urlopen", lambda req, timeout=None: reply)
    assert release_download.github_latest_tag("o", "r") == "v1.2.3"


def _limited_api_then_redirect(final_url, req, timeout=None):
    """The API answers 403; the release page redirects to ``final_url``."""
    return rate_limited(req) if "api.github.com" in req.full_url else Reply(url=final_url)


def _recording_urlopen(seen, req, timeout=None):
    seen[req.full_url.split("/")[2]] = req.get_header("Authorization")
    return _limited_api_then_redirect("https://github.com/o/r/releases/tag/v9", req)


def test_a_rate_limited_api_falls_back_to_the_release_redirect(monkeypatch, capsys):
    monkeypatch.setattr(release_download.urllib.request, "urlopen",
                        partial(_limited_api_then_redirect, "https://github.com/mpv-player/mpv/releases/tag/v0.41.0"))
    assert release_download.github_latest_tag("mpv-player", "mpv") == "v0.41.0"
    assert "trying the release page" in capsys.readouterr().out


def test_when_both_fail_the_answer_is_none(monkeypatch):
    monkeypatch.setattr(release_download.urllib.request, "urlopen", rate_limited)
    assert release_download.github_latest_tag("o", "r") is None


@pytest.mark.parametrize("final_url", ["https://github.com/o/r/releases", "https://example.com/"])
def test_a_redirect_that_is_not_a_tag_page_gives_none(monkeypatch, final_url):
    monkeypatch.setattr(release_download.urllib.request, "urlopen", partial(_limited_api_then_redirect, final_url))
    assert release_download.github_latest_tag("o", "r") is None


def test_the_token_is_sent_to_the_api_only(monkeypatch):
    seen = {}

    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setattr(release_download.urllib.request, "urlopen", partial(_recording_urlopen, seen))
    assert release_download.github_latest_tag("o", "r") == "v9"
    assert seen == {"api.github.com": "Bearer secret", "github.com": None}
