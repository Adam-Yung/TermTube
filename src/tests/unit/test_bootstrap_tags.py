"""bootstrap._github_latest_tag: the API first, the release page's redirect when the API is rate-limited."""

import io
import urllib.error

import pytest

from src import bootstrap


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
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda req, timeout=None: Reply(b'{"tag_name": "v1.2.3"}'))
    assert bootstrap._github_latest_tag("o", "r") == "v1.2.3"


def test_a_rate_limited_api_falls_back_to_the_release_redirect(monkeypatch, capsys):
    def urlopen(req, timeout=None):
        if "api.github.com" in req.full_url:
            return rate_limited(req)
        return Reply(url="https://github.com/mpv-player/mpv/releases/tag/v0.41.0")

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", urlopen)
    assert bootstrap._github_latest_tag("mpv-player", "mpv") == "v0.41.0"
    assert "trying the release page" in capsys.readouterr().out


def test_when_both_fail_the_answer_is_none(monkeypatch):
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", rate_limited)
    assert bootstrap._github_latest_tag("o", "r") is None


@pytest.mark.parametrize("final_url", ["https://github.com/o/r/releases", "https://example.com/"])
def test_a_redirect_that_is_not_a_tag_page_gives_none(monkeypatch, final_url):
    def urlopen(req, timeout=None):
        return rate_limited(req) if "api.github.com" in req.full_url else Reply(url=final_url)

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", urlopen)
    assert bootstrap._github_latest_tag("o", "r") is None


def test_the_token_is_sent_to_the_api_only(monkeypatch):
    seen = {}

    def urlopen(req, timeout=None):
        seen[req.full_url.split("/")[2]] = req.get_header("Authorization")
        return rate_limited(req) if "api.github.com" in req.full_url else Reply(url="https://github.com/o/r/releases/tag/v9")

    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", urlopen)
    assert bootstrap._github_latest_tag("o", "r") == "v9"
    assert seen == {"api.github.com": "Bearer secret", "github.com": None}
