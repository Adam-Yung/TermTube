"""Integration tests for mpv IPC command generation with mocked socket."""

import json
import socket
import sys
from unittest.mock import patch, MagicMock, call

import pytest

from src.player import (
    send_ipc_command,
    poll_audio_properties,
    _poll_audio_properties_batched,
    _cookie_args_to_ytdl_raw,
)

# socket.AF_UNIX does not exist on Windows — skip Unix-socket tests there.
_SKIP_UNIX = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix AF_UNIX socket tests not applicable on Windows",
)


def _make_mock_socket(responses: list[dict] | None = None, raise_on_connect=False):
    """Create a mock socket that returns JSON responses line-by-line."""
    mock_sock = MagicMock()

    if raise_on_connect:
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")
        return mock_sock

    if responses is None:
        responses = []

    response_data = b"".join(
        (json.dumps(r) + "\n").encode() for r in responses
    )

    recv_calls = [response_data, b""]
    mock_sock.recv.side_effect = recv_calls
    return mock_sock


@_SKIP_UNIX
class TestSendIpcCommand:
    """Tests for send_ipc_command JSON formatting."""

    def test_formats_json_correctly(self):
        response = {"error": "success", "data": 42.5}
        mock_sock = _make_mock_socket([response])

        with patch("src.player.socket.socket", return_value=mock_sock):
            result = send_ipc_command(
                {"command": ["get_property", "time-pos"]},
                socket_path="/tmp/test.sock",
            )

        sent_data = mock_sock.sendall.call_args[0][0]
        sent_json = json.loads(sent_data.decode().strip())
        assert sent_json == {"command": ["get_property", "time-pos"]}
        assert result == response

    def test_payload_ends_with_newline(self):
        mock_sock = _make_mock_socket([{"error": "success", "data": None}])

        with patch("src.player.socket.socket", return_value=mock_sock):
            send_ipc_command(
                {"command": ["cycle", "pause"]},
                socket_path="/tmp/test.sock",
            )

        sent_data = mock_sock.sendall.call_args[0][0]
        assert sent_data.endswith(b"\n")

    def test_returns_none_on_empty_response(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""

        with patch("src.player.socket.socket", return_value=mock_sock):
            result = send_ipc_command(
                {"command": ["get_property", "volume"]},
                socket_path="/tmp/test.sock",
            )

        assert result is None

    def test_returns_none_on_connection_error(self):
        mock_sock = _make_mock_socket(raise_on_connect=True)

        with patch("src.player.socket.socket", return_value=mock_sock):
            result = send_ipc_command(
                {"command": ["get_property", "time-pos"]},
                socket_path="/tmp/test.sock",
            )

        assert result is None

    def test_complex_command_serialization(self):
        mock_sock = _make_mock_socket([{"error": "success"}])

        with patch("src.player.socket.socket", return_value=mock_sock):
            send_ipc_command(
                {"command": ["set_property", "volume", 75]},
                socket_path="/tmp/test.sock",
            )

        sent_data = mock_sock.sendall.call_args[0][0]
        sent_json = json.loads(sent_data.decode().strip())
        assert sent_json["command"] == ["set_property", "volume", 75]


@_SKIP_UNIX
class TestPollAudioProperties:
    """Tests for poll_audio_properties batched response parsing."""

    def test_parses_batched_responses(self):
        responses = [
            {"error": "success", "data": 45.2, "request_id": 0},
            {"error": "success", "data": 300.0, "request_id": 1},
            {"error": "success", "data": False, "request_id": 2},
        ]
        response_bytes = b"".join(
            (json.dumps(r) + "\n").encode() for r in responses
        )

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [response_bytes, b""]

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            pos, dur, paused = poll_audio_properties(socket_path="/tmp/test.sock")

        assert pos == pytest.approx(45.2)
        assert dur == pytest.approx(300.0)
        assert paused is False

    def test_parses_paused_state(self):
        responses = [
            {"error": "success", "data": 10.0, "request_id": 0},
            {"error": "success", "data": 200.0, "request_id": 1},
            {"error": "success", "data": True, "request_id": 2},
        ]
        response_bytes = b"".join(
            (json.dumps(r) + "\n").encode() for r in responses
        )

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [response_bytes, b""]

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            pos, dur, paused = poll_audio_properties(socket_path="/tmp/test.sock")

        assert pos == pytest.approx(10.0)
        assert dur == pytest.approx(200.0)
        assert paused is True

    def test_returns_none_none_false_on_connection_error(self):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            pos, dur, paused = poll_audio_properties(socket_path="/tmp/test.sock")

        assert pos is None
        assert dur is None
        assert paused is False

    def test_returns_none_none_false_on_file_not_found(self):
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = FileNotFoundError("Socket not found")

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            pos, dur, paused = poll_audio_properties(socket_path="/tmp/test.sock")

        assert pos is None
        assert dur is None
        assert paused is False

    def test_sends_three_batched_requests(self):
        responses = [
            {"error": "success", "data": 0.0, "request_id": 0},
            {"error": "success", "data": 60.0, "request_id": 1},
            {"error": "success", "data": False, "request_id": 2},
        ]
        response_bytes = b"".join(
            (json.dumps(r) + "\n").encode() for r in responses
        )

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [response_bytes, b""]

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            _poll_audio_properties_batched(socket_path="/tmp/test.sock")

        assert mock_sock.sendall.call_count == 3
        for i, prop in enumerate(("time-pos", "duration", "pause")):
            sent = json.loads(mock_sock.sendall.call_args_list[i][0][0].decode().strip())
            assert sent["command"] == ["get_property", prop]
            assert sent["request_id"] == i

    def test_handles_partial_responses(self):
        """When only some responses arrive before timeout, missing props are None."""
        response_bytes = (json.dumps(
            {"error": "success", "data": 22.0, "request_id": 0}
        ) + "\n").encode()

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [response_bytes, socket.timeout("timed out")]

        with patch("src.player.IS_WINDOWS", False), \
             patch("src.player.socket.socket", return_value=mock_sock):
            pos, dur, paused = _poll_audio_properties_batched(socket_path="/tmp/test.sock")

        assert pos == pytest.approx(22.0)
        assert dur is None
        assert paused is False


class TestCookieArgsToYtdlRaw:
    """Tests for _cookie_args_to_ytdl_raw formatting."""

    def test_cookies_file_flag(self):
        result = _cookie_args_to_ytdl_raw(["--cookies", "/path/to/cookies.txt"])
        assert result == "cookies=/path/to/cookies.txt"

    def test_cookies_from_browser_flag(self):
        result = _cookie_args_to_ytdl_raw(["--cookies-from-browser", "chrome"])
        assert result == "cookies-from-browser=chrome"

    def test_multiple_flags(self):
        args = ["--cookies", "/tmp/c.txt", "--cookies-from-browser", "firefox"]
        result = _cookie_args_to_ytdl_raw(args)
        assert "cookies=/tmp/c.txt" in result
        assert "cookies-from-browser=firefox" in result
        assert result == "cookies=/tmp/c.txt,cookies-from-browser=firefox"

    def test_empty_args(self):
        result = _cookie_args_to_ytdl_raw([])
        assert result == ""

    def test_ignores_standalone_flags(self):
        result = _cookie_args_to_ytdl_raw(["--no-check-certificate"])
        assert result == ""
