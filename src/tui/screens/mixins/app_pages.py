from __future__ import annotations


class AppPagesMixin:
    """The pages every full screen opens the same way: Help and Settings."""

    def action_help(self) -> None:
        from src.tui.screens.help_screen import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_settings(self) -> None:
        from src.tui.screens.settings_modal import SettingsModal

        self.app.push_screen(SettingsModal())
