from __future__ import annotations

from functools import partial

from textual import work

from src.strings import text


class FeedPromptsMixin:
    """The dialogs around account feeds and startup: empty feed, yt-dlp update, cookies and the image warning.

    Needs ``_current_tab``, ``_load_view``, ``_list``, ``notify`` and ``app`` from the screen.
    """

    def _maybe_show_image_warning(self) -> None:
        from src.tui.widgets.thumbnail_widget import _HAS_TEXTUAL_IMAGE

        if _HAS_TEXTUAL_IMAGE or self.app.config.get("thumbnail_warning_dismissed", False):
            return
        from src.tui.screens.image_warning_modal import ImageWarningModal

        self.app.push_screen(ImageWarningModal(), partial(self._on_image_warning_closed, self.app.config))

    def _on_image_warning_closed(self, config, never_show: bool) -> None:
        if never_show:
            config.set("thumbnail_warning_dismissed", True)
            config.save()

    def _show_empty_feed_modal(self, feed_key: str) -> None:
        from src.tui.screens.empty_feed_modal import EmptyFeedModal

        self.app.push_screen(EmptyFeedModal(), partial(self._on_empty_feed_choice, feed_key))

    def _on_empty_feed_choice(self, feed_key: str, choice: str) -> None:
        if choice == "update":
            self._run_ytdlp_update(reload_tab=feed_key)
        elif choice == "refresh":
            self._refresh_account(feed_key)
        elif choice == "settings":
            from src.tui.screens.settings_modal import SettingsModal

            self.app.push_screen(SettingsModal())

    def _prewarm_cookies(self) -> None:
        from src import cookies

        cookies.prewarm(self.app.config)

    def _refresh_account(self, feed_key: str) -> None:
        """Forget the cookie jar (the next load re-reads the browser) and reload the feed."""
        from src import cookies

        cookies.invalidate()
        self.app.cache.clear_feed(feed_key)
        self._load_view(self._current_tab)

    def _prompt_ytdlp_update(self, feed_key: str, error_detail: str = "") -> None:
        from src.tui.screens.ytdlp_update_modal import YtdlpUpdateModal

        self.app.push_screen(YtdlpUpdateModal(error_detail), partial(self._on_update_choice, feed_key))

    def _on_update_choice(self, feed_key: str, choice: str) -> None:
        if choice == "update":
            self._run_ytdlp_update(reload_tab=feed_key)
        else:
            self._list().set_error_message(text("main_screen.feed_failed"))

    @work(thread=True)
    def _run_ytdlp_update(self, *, reload_tab: str | None = None) -> None:
        from src.updater import update_ytdlp

        call = self.app.call_from_thread
        call(self.notify, text("main_screen.updating_ytdlp"), timeout=3)
        if not update_ytdlp(verbose=False):
            call(self.notify, text("main_screen.ytdlp_update_failed"), severity="error", timeout=6)
        elif reload_tab:
            call(self.notify, text("main_screen.ytdlp_updated_reloading"), timeout=4)
            call(self._load_view, reload_tab)
        else:
            call(self.notify, text("main_screen.ytdlp_updated"), timeout=5)
