"""scripts/diagnose-rss.py: the report helpers, with no network."""

import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "diagnose-rss.py"


@pytest.fixture(scope="module")
def diag():
    spec = importlib.util.spec_from_file_location("diagnose_rss", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse(io.BytesIO):
    def __init__(self, status, headers, body):
        super().__init__(body)
        self.status, self.headers = status, headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, outcome):
        self.outcome, self.requests = outcome, []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class Headers(dict):
    def items(self):
        return super().items()


def test_probe_reads_a_feed(diag):
    opener = FakeOpener(FakeResponse(200, Headers({"Content-Type": "application/atom+xml"}), b"<?xml?><feed>"))
    result = diag.probe("https://x/feed", "agent/1", opener=opener)
    assert result["status"] == 200 and opener.requests[0].get_header("User-agent") == "agent/1"
    assert diag.describe(result).startswith("200 ATOM")


def test_probe_reports_http_errors_with_the_body(diag):
    error = urllib.error.HTTPError("u", 404, "nf", Headers({"Server": "ESF"}), io.BytesIO(b"<html>not found</html>"))
    result = diag.probe("https://x/feed", opener=FakeOpener(error))
    line = diag.describe(result)
    assert result["status"] == 404 and line.startswith("404 HTML") and "server=ESF" in line and "not found" in line


def test_probe_reports_network_errors(diag):
    result = diag.probe("https://x/feed", opener=FakeOpener(urllib.error.URLError("reset")))
    assert result["status"] is None and diag.describe(result).startswith("ERROR URLError")


def test_probe_sends_no_cookie_or_auth_header(diag):
    opener = FakeOpener(FakeResponse(200, Headers(), b""))
    diag.probe("https://x/feed", "agent", opener=opener)
    assert not {k.lower() for k in opener.requests[0].headers} & {"cookie", "authorization"}


@pytest.mark.parametrize("statuses,expected", [
    ([200, 200], "works for every"),
    ([200, 404], "1 of 2"),
    ([404, 404], "endpoint is down or blocked"),
    ([403, None], "No probe returned 200"),
])
def test_verdict(diag, statuses, expected):
    assert expected in diag.verdict(statuses)


def test_script_only_targets_youtube():
    import re

    hosts = set(re.findall(r"https?://([\w.-]+)", SCRIPT.read_text()))
    hosts -= {"www.feedly.com"}  # only inside a user-agent string
    assert hosts and all(h == "youtube.com" or h.endswith(".youtube.com") for h in hosts)
