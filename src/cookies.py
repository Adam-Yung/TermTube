"""TermTube v2 — cookie lifecycle manager.

Flow:
1. cookies.txt exists and is < cookie_max_age_days old  →  use silently (ok)
2. Missing or stale                                     →  auto_refresh()
3. auto_refresh fails                                   →  status = "stale"/"missing"
   UI layer shows a non-blocking banner; user presses C to open wizard.

All methods MUST be called from a worker thread (they can block).
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Literal

import logger
from config import Config

CookieStatus = Literal["ok", "stale", "missing"]

# Browsers yt-dlp can extract cookies from
SUPPORTED_BROWSERS = [
    "chrome",
    "chromium",
    "firefox",
    "safari",
    "edge",
    "opera",
    "brave",
    "vivaldi",
]


class CookieManager:
    def __init__(self, config: Config) -> None:
        self._config = config

    def status(self) -> CookieStatus:
        p = self._config.cookies_file
        if not p.exists():
            return "missing"
        age_days = (time.time() - p.stat().st_mtime) / 86400
        if age_days > self._config.cookie_max_age_days:
            return "stale"
        return "ok"

    def is_fresh(self) -> bool:
        return self.status() == "ok"

    def auto_refresh(self, browser: str | None = None) -> bool:
        """Attempt to refresh cookies from browser.

        Saves browser choice to config on success.
        Returns True on success.  MUST be called from a worker thread.
        """
        b = browser or self._config.browser or "chrome"
        dest = self._config.cookies_file
        dest.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "yt-dlp",
            "--cookies-from-browser", b,
            "--cookies", str(dest),
            "--skip-download",
            "--quiet",
            "https://www.youtube.com",
        ]

        logger.info("cookie refresh: browser=%s", b)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and dest.exists():
                self._config.persist_browser(b)
                logger.info("cookie refresh success, saved to %s", dest)
                return True
            err = result.stderr.decode(errors="replace").strip()
            logger.warning("cookie refresh failed (rc=%d): %s", result.returncode, err[:200])
            return False
        except subprocess.TimeoutExpired:
            logger.warning("cookie refresh timed out")
            return False
        except FileNotFoundError:
            logger.warning("yt-dlp not found for cookie refresh")
            return False
        except Exception as exc:
            logger.warning("cookie refresh error: %s", exc)
            return False

    def validate(self) -> bool:
        """Quick test: try fetching a small YouTube page with current cookies."""
        p = self._config.cookies_file
        if not p.exists():
            return False
        cmd = [
            "yt-dlp",
            "--cookies", str(p),
            "--skip-download",
            "--quiet",
            "--simulate",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def detect_installed_browsers() -> list[str]:
        """Return subset of SUPPORTED_BROWSERS that appear to be installed."""
        import shutil
        import sys
        found = []
        check_map = {
            "chrome":   ["google-chrome", "chrome", "chromium-browser"],
            "chromium": ["chromium", "chromium-browser"],
            "firefox":  ["firefox"],
            "safari":   ["safari"],   # macOS only
            "edge":     ["microsoft-edge", "msedge"],
            "opera":    ["opera"],
            "brave":    ["brave-browser", "brave"],
            "vivaldi":  ["vivaldi"],
        }
        for browser, bins in check_map.items():
            for b in bins:
                if shutil.which(b):
                    found.append(browser)
                    break
            else:
                # macOS app bundle check
                if sys.platform == "darwin":
                    app_names = {
                        "safari": "Safari.app",
                        "chrome": "Google Chrome.app",
                        "firefox": "Firefox.app",
                        "edge": "Microsoft Edge.app",
                        "brave": "Brave Browser.app",
                        "opera": "Opera.app",
                        "vivaldi": "Vivaldi.app",
                    }
                    app = app_names.get(browser)
                    if app:
                        paths = [
                            Path(f"/Applications/{app}"),
                            Path(f"~/Applications/{app}").expanduser(),
                        ]
                        if any(p.exists() for p in paths):
                            found.append(browser)
        return found
