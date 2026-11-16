from __future__ import annotations

import threading
import time

from src import logger

_MAX_AGE_S = 600

_jar = None
_jar_extracted_at = 0.0
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


def _fresh() -> bool:
    return _jar is not None and time.time() - _jar_extracted_at < _MAX_AGE_S


def get_cookiejar(config):
    """Browser cookies, extracted once and reused for ``_MAX_AGE_S`` seconds.

    Extraction takes 5-15 s on a cold browser profile. The timeout lets a
    mid-session account switch in the browser take effect.
    """
    global _jar, _jar_extracted_at
    if _fresh():
        return _jar
    with _lock:
        if _fresh():
            return _jar
        browser = resolve_browser(config)
        if not browser:
            return None
        try:
            from yt_dlp.cookies import extract_cookies_from_browser

            _jar = extract_cookies_from_browser(browser)
            _jar_extracted_at = time.time()
            logger.debug("extracted cookies from %s", browser)
        except Exception as exc:
            logger.debug("cookie extraction failed: %s", exc)
            return None
    return _jar
