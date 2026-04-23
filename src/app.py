"""Main application router — page stack navigation."""

from __future__ import annotations
import os
import sys

from src.cache import Cache
from src.config import Config
from src.ui import gum

# Lazy imports of pages (avoid slow startup)

_MENU_ITEMS = [
    ("🏠  Home          Recommended feed",       "home"),
    ("🔍  Search        Find videos",            "search"),
    ("📺  Subscriptions Your subscribed channels","subscriptions"),
    ("📁  Library       Locally saved files",    "library"),
    ("📜  History       Recently watched",       "history"),
    ("⚙   Settings      View config info",       "settings"),
    ("✕   Quit",                                 "quit"),
]

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_CYAN  = "\033[36m"
_GRAY  = "\033[90m"


def _print_logo() -> None:
    os.system("clear")
    logo = rf"""
  {_CYAN}{_BOLD}╔╦╗╦ ╦  ╦ ╦┌─┐┬ ┬╔╦╗┬ ┬┌┐ ┌─┐{_RESET}
  {_CYAN} ║ ╚╦╝  ╚╦╝│ ││ │ ║ │ │├┴┐├┤ {_RESET}
  {_CYAN} ╩  ╩    ╩ └─┘└─┘ ╩ └─┘└─┘└─┘{_RESET}
  {_GRAY}YouTube TUI powered by yt-dlp + fzf + gum{_RESET}
"""
    print(logo)


def _show_main_menu() -> str | None:
    """Show the main navigation menu. Returns page key or None to quit."""
    import subprocess

    labels = [item[0] for item in _MENU_ITEMS]
    keys   = {item[0]: item[1] for item in _MENU_ITEMS}

    _print_logo()

    result = subprocess.run(
        [
            "fzf",
            "--ansi",
            "--no-sort",
            "--layout=reverse-list",
            "--border=rounded",
            "--color=header:italic,border:240",
            "--pointer=▶",
            "--prompt=  ▶  ",
            "--header",
            f"  {_GRAY}Navigate with ↑↓ / jk  │  Enter to select  │  q to quit{_RESET}",
            "--bind=j:down,k:up,q:abort",
            "--height=~14",
        ],
        input="\n".join(labels),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    selected_label = result.stdout.strip()
    return keys.get(selected_label)


def _show_settings(config: Config) -> None:
    os.system("clear")
    gum.header("⚙  Settings", "MyYouTube Configuration")
    print()

    cf = config.cookies_file
    cf_path = config.cookies_file_path
    source = config.cookie_source

    print(f"  {'Config file':<22} {config.path}")
    print(f"  {'Cookie source':<22} {source}")
    if cf_path and not cf:
        print(f"  {'cookies.txt':<22} \033[33m⚠ configured but not found at {cf_path}\033[0m")
        print()
        print(f"  \033[90mRun 'myt --cookies-help' for instructions on getting a cookies.txt.\033[0m")
    print(f"  {'Video dir':<22} {config.video_dir}")
    print(f"  {'Audio dir':<22} {config.audio_dir}")
    print(f"  {'Preferred player':<22} {config.preferred_player}")
    print(f"  {'Quality':<22} {config.preferred_quality}")
    print()
    input("Press Enter to go back…")


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache = Cache({
            "home":          config.cache_ttl("home"),
            "subscriptions": config.cache_ttl("subscriptions"),
            "search":        config.cache_ttl("search"),
            "metadata":      config.cache_ttl("metadata"),
        })

    def run(self) -> None:
        while True:
            page = _show_main_menu()

            if page is None or page == "quit":
                os.system("clear")
                print(f"  {_CYAN}Goodbye!{_RESET}")
                sys.exit(0)

            self._route(page)

    def _route(self, page: str) -> None:
        from src.pages import (
            home, search, subscriptions, history_page, library_page, video_detail
        )

        if page == "home":
            video_id = home.run(self.config, self.cache)
        elif page == "search":
            video_id = search.run(self.config, self.cache)
        elif page == "subscriptions":
            video_id = subscriptions.run(self.config, self.cache)
        elif page == "history":
            video_id = history_page.run(self.config, self.cache)
        elif page == "library":
            video_id = library_page.run(self.config, self.cache)
        elif page == "settings":
            _show_settings(self.config)
            return
        else:
            return

        if video_id:
            video_detail.run(video_id, self.config, self.cache)
