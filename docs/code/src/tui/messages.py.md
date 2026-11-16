# src/tui/messages.py

Textual `Message` classes shared across screens and mixins. Messages that belong to one widget stay in that widget's file.

`PlayerStateUpdated` carries one mpv poll result to the UI: `pos`, `dur`, `paused`, and `playing`. `playing=False` means playback stopped
and `pos`/`dur` are 0. The audio worker posts it with `self.app.screen.post_message(...)`; `App.post_message` does not reach screens
(`AGENTS.md`). It is posted to the active screen, so a modal on top receives it and must forward or ignore it.
