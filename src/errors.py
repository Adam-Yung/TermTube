"""Typed source errors: why a yt-dlp or InnerTube fetch failed, with the message the list shows."""

from __future__ import annotations

import socket
import urllib.error

SIGN_IN_MESSAGE = (
    "YouTube asked for a sign-in. Sign in to YouTube in the browser TermTube reads (Settings ,), then press r."
)

_RATE_MARKERS = ("http error 429", "too many requests", "rate limit", "rate-limit")
_SIGN_IN_MARKERS = ("sign in", "login required", "http error 401", "http error 403", "status 401", "status 403")
_NETWORK_MARKERS = (
    "urlopen error", "name or service not known", "nodename nor servname", "temporary failure in name resolution",
    "network is unreachable", "timed out", "connection reset", "connection refused", "connection aborted",
    "transporterror", "remote end closed", "no route to host", "http error 5",
)


class SourceError(Exception):
    """A real fetch failure (an honestly empty feed is not one). ``message`` is the short text for the user."""

    message = "Could not load this list."

    def __init__(self, detail: str = "", *, retry_after: float | None = None) -> None:
        super().__init__(detail or self.message)
        self.detail = detail
        self.retry_after = retry_after


class SignInRequired(SourceError):
    message = SIGN_IN_MESSAGE


class RateLimited(SourceError):
    message = "YouTube is rate limiting this IP · try again in a minute"


class NetworkDown(SourceError):
    message = "Network error · r to retry"


class ExtractionFailed(SourceError):
    message = "YouTube changed something and yt-dlp could not read it."


def classify(exc: BaseException | str, *, status: int | None = None) -> SourceError:
    """The typed error for a yt-dlp/HTTP failure, from its text and, when known, the HTTP status."""
    if isinstance(exc, SourceError):
        return exc
    text = str(exc)
    low = text.lower()
    inner = getattr(exc, "exc_info", None)
    inner = inner[1] if inner else exc
    if status == 429 or any(m in low for m in _RATE_MARKERS):
        return RateLimited(text)
    if status in (401, 403) or any(m in low for m in _SIGN_IN_MARKERS):
        return SignInRequired(text)
    is_net = isinstance(inner, (urllib.error.URLError, socket.error, TimeoutError, ConnectionError))
    if (status is not None and status >= 500) or is_net or any(m in low for m in _NETWORK_MARKERS):
        return NetworkDown(text)
    return ExtractionFailed(text)
