from __future__ import annotations

import threading

from src import logger

_KEPT_DOMAINS = ("youtube.com", "google.com")

_jar = None
_prewarmed = False
_lock = threading.Lock()


def resolve_browser(config) -> str | None:
    """Return the browser to read cookies from, or None for unauthenticated use."""
    browser = config.get("browser", "auto")
    if not browser or browser.lower() == "none":
        return None
    from src.browsers import detect_installed_browsers, is_auto_browser

    if is_auto_browser(browser):
        detected = detect_installed_browsers()
        return detected[0]["name"] if detected else None
    return browser


def _keep(domain: str) -> bool:
    domain = domain.lstrip(".").lower()
    return any(domain == d or domain.endswith("." + d) for d in _KEPT_DOMAINS)


def _narrow(jar) -> None:
    """Drop every cookie that is not for YouTube or Google; the rest of the browser's cookies never stay in memory."""
    for cookie in [c for c in jar if not _keep(c.domain)]:
        jar.clear(cookie.domain, cookie.path, cookie.name)


def is_auth_failure(exc: BaseException) -> bool:
    """True when a yt-dlp error reads like an expired or missing sign-in, so a fresh jar might help."""
    from src.errors import SignInRequired, classify

    return isinstance(classify(exc), SignInRequired)


def invalidate() -> None:
    """Forget the jar; the next ``get_cookiejar`` call re-reads the browser."""
    global _jar
    with _lock:
        _jar = None


def prewarm(config) -> bool:
    """Start the cookie read in a background thread so Home finds a warm jar. True when one was started.

    Never when the browser is ``none`` or unresolved, when ``cookie_prewarm`` is off, or a second time.
    """
    global _prewarmed
    if not config.cookie_prewarm or resolve_browser(config) is None:
        return False
    with _lock:
        if _prewarmed or _jar is not None:
            return False
        _prewarmed = True
    threading.Thread(target=get_cookiejar, args=(config,), daemon=True, name="cookie-prewarm").start()
    return True


def get_cookiejar(config):
    """The narrowed browser cookie jar, extracted on first use and kept until ``invalidate``.

    Extraction takes 5-15 s on a cold browser profile, so callers run in worker threads.
    """
    global _jar
    with _lock:
        if _jar is not None:
            return _jar
        browser = resolve_browser(config)
        if not browser:
            return None
        try:
            from yt_dlp.cookies import extract_cookies_from_browser

            jar = extract_cookies_from_browser(browser)
            _narrow(jar)
            _jar = jar
            logger.stage("cookie jar ready")
            logger.debug("extracted cookies from %s", browser)
        except Exception as exc:
            logger.debug("cookie extraction failed: %s", exc)
            return None
    return _jar
