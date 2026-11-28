"""Cookie prewarm: reads only when a browser resolves and the setting is on, and only once."""

import pytest

import src.cookies as cookies
from src.config import Config


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(cookies, "_jar", None)
    monkeypatch.setattr(cookies, "_prewarmed", False)


class _InlineThread:
    """A Thread that runs its target on ``start``, on the caller's thread."""

    def __init__(self, target, args=(), **kw):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def reads(monkeypatch):
    calls = []
    monkeypatch.setattr(cookies, "get_cookiejar", lambda config: calls.append(1))

    monkeypatch.setattr(cookies.threading, "Thread", _InlineThread)
    return calls


def _config(tmp_path, **data):
    config = Config(path=str(tmp_path / "config.yaml"))
    config._data.update(data)
    return config


def test_browser_none_reads_nothing(tmp_path, reads):
    assert cookies.prewarm(_config(tmp_path, browser="none")) is False
    assert reads == []


def test_prewarm_off_reads_nothing(tmp_path, reads):
    assert cookies.prewarm(_config(tmp_path, browser="firefox", cookie_prewarm=False)) is False
    assert reads == []


def test_prewarm_defaults_on_and_runs_once(tmp_path, reads):
    config = _config(tmp_path, browser="firefox")
    assert config.cookie_prewarm is True
    assert cookies.prewarm(config) is True
    assert cookies.prewarm(config) is False
    assert reads == [1]
