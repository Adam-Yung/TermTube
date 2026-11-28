"""A poll that times out leaves its replies in the pooled socket; the next poll must not take them as its own."""
import socket

import pytest

from src import mpv_ipc


@pytest.fixture
def mpv_end(tmp_path):
    ours, theirs = socket.socketpair()
    path = str(tmp_path / "mpv.sock")
    mpv_ipc._persistent_sockets[path] = ours
    yield path, theirs
    mpv_ipc.close_all()
    theirs.close()


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix socket transport")
def test_a_timed_out_poll_drops_the_socket_its_late_replies_would_land_in(mpv_end, monkeypatch):
    path, _theirs = mpv_end
    monkeypatch.setattr(mpv_ipc, "_POLL_TIMEOUT", 0.05)
    assert mpv_ipc._poll_audio_properties_batched(socket_path=path) == (None, None, False)
    assert path not in mpv_ipc._persistent_sockets
