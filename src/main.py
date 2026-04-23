#!/usr/bin/env python3
"""MyYouTube entry point."""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="myt",
        description="MyYouTube — YouTube TUI powered by yt-dlp + Textual",
    )
    parser.add_argument("--config", metavar="FILE", help="Path to config YAML")
    parser.add_argument("--cookies-help", action="store_true", help="Show cookies.txt setup instructions")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cached feeds and metadata")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging to stderr and ~/.cache/myyoutube/debug.log")
    parser.add_argument("--version", action="store_true", help="Show version")
    args = parser.parse_args()

    # Set up logging before anything else
    from src import logger
    logger.setup(debug=args.debug)

    if args.version:
        print("MyYouTube 0.1.0")
        sys.exit(0)

    if args.cookies_help:
        from src.deps import print_cookies_help
        print_cookies_help()
        sys.exit(0)

    # Dependency check
    from src.deps import check_dependencies
    if not check_dependencies():
        sys.exit(1)

    # Load config
    from src.config import Config
    config = Config(args.config)

    if args.clear_cache:
        from src.cache import Cache
        cache = Cache({})
        cache.clear_all()
        print("Cache cleared.")
        sys.exit(0)

    # Warn if no cookie source is configured
    if not config.cookie_args:
        print("\033[33m⚠ No cookie source configured. Home feed and subscriptions require authentication.\033[0m")
        print("  Run: myt --cookies-help  for setup instructions.\n")

    # Launch Textual TUI
    from src.tui.app import MyYouTubeApp
    app = MyYouTubeApp(config)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
