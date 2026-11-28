"""Search suggestions: the reply parser, the fetch (no network), the config switch."""

import json
from unittest.mock import patch

import pytest

from src import innertube
from src.config import Config


def test_parse_reads_the_suggestion_array():
    raw = json.dumps(["rust", ["rust tutorial", " rust game ", "", 5, "rust"], {"x": 1}])
    assert innertube.parse_suggestions(raw) == ["rust tutorial", "rust game", "rust"]
    assert innertube.parse_suggestions(raw.encode()) == ["rust tutorial", "rust game", "rust"]


@pytest.mark.parametrize(
    "raw", ["", "not json", "{}", "[]", '["q"]', '["q", "str"]', '["q", {"a": 1}]', b"\xff\xfe\x00", "null"]
)
def test_parse_malformed_is_empty(raw):
    assert innertube.parse_suggestions(raw) == []


def test_fetch_builds_an_anonymous_request_and_parses():
    reply = (200, b'["py", ["python", "pytorch"]]')
    with patch.object(innertube, "_request", return_value=reply) as req:
        assert innertube.fetch_suggestions("py & co") == ["python", "pytorch"]
    args, kwargs = req.call_args
    assert args[:2] == ("GET", "suggestqueries.google.com")
    assert "client=firefox&ds=yt&q=py+%26+co" in args[2]
    assert "Cookie" not in kwargs["headers"] and "Authorization" not in kwargs["headers"]
    assert kwargs["max_bytes"] == 16 * 1024 and kwargs["timeout"] == 2


@pytest.mark.parametrize("reply", [None, (500, b'["q", ["a"]]'), (200, b"garbage")])
def test_fetch_fails_silent(reply):
    with patch.object(innertube, "_request", return_value=reply):
        assert innertube.fetch_suggestions("abc") == []


class _EndlessReply:
    status = 200

    def read(self, n=None):
        return b"x" * n


class _EndlessConn:
    def request(self, *a, **k):
        pass

    def getresponse(self):
        return _EndlessReply()


def test_request_cuts_an_oversized_body_and_drops_the_connection():
    with patch.object(innertube, "_connection", return_value=(_EndlessConn(), False)), \
            patch.object(innertube, "_drop_connection") as drop:
        status, data = innertube._request("GET", "h", "/p", body=None, headers={}, timeout=2, max_bytes=10)
    assert (status, len(data)) == (200, 10) and drop.called


def test_config_switch_defaults_on_and_only_false_turns_it_off(tmp_path):
    config = Config(path=str(tmp_path / "c.yaml"))
    assert config.search_suggestions_enabled
    for value, expected in ((False, False), ("false", True), (None, True), (0, True)):
        config._data["search_suggestions"] = value
        assert config.search_suggestions_enabled is expected
