"""TermTube v2 — application entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="termtube",
        description="TermTube v2 — YouTube in your terminal",
    )
    p.add_argument("--version", action="version", version="TermTube v2.0.0")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    p.add_argument(
        "--level",
        default="ALL",
        choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level (only applies with --debug)",
    )
    p.add_argument("--config", metavar="PATH", help="Path to config file (overrides default)")
    p.add_argument("--clear-cache", action="store_true", help="Clear all cached data and exit")
    p.add_argument("--setup-cookies", nargs="?", const="auto", metavar="BROWSER",
                   help="Run cookie setup wizard (optionally specify browser)")
    p.add_argument("--cookies-help", action="store_true", help="Show cookie setup instructions")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    import logger as _logger
    _logger.setup(debug=args.debug, level=args.level)

    if args.cookies_help:
        from deps import print_cookies_help
        print_cookies_help()
        return

    from config import Config, CONFIG_PATH
    config = Config()
    if args.config:
        from config import CONFIG_PATH as _cp
        import config as _cfg_mod
        _cfg_mod.CONFIG_PATH = Path(args.config)
    config.load()

    if args.clear_cache:
        import cache as _cache
        _cache.clear_all()
        print("Cache cleared.")
        return

    if args.setup_cookies:
        from cookies import CookieManager
        mgr = CookieManager(config)
        browser = None if args.setup_cookies == "auto" else args.setup_cookies
        ok = mgr.auto_refresh(browser)
        if ok:
            print(f"Cookies refreshed successfully → {config.cookies_file}")
        else:
            from deps import print_cookies_help
            print("Automatic cookie fetch failed.")
            print_cookies_help()
        return

    from deps import check_all, assert_required
    assert_required(check_all())

    # Validate Python version
    if sys.version_info < (3, 11):
        print("TermTube requires Python 3.11+", file=sys.stderr)
        sys.exit(1)

    # Import textual_image early (terminal detection at import time)
    try:
        import textual_image.widget  # noqa: F401
    except ImportError:
        pass

    from tui.app import TermTubeApp
    app = TermTubeApp(config)
    app.run()


if __name__ == "__main__":
    main()
