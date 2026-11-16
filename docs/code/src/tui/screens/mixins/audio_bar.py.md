# src/tui/screens/mixins/audio_bar.py

`AudioBarMixin` mirrors `app.audio` (`docs/code/src/tui/audio_controller.py.md`) into the screen's own `ActionBar`. `MainScreen` and `ChannelScreen` use it; neither owns audio.

- `_sync_player_bar()` pulls the controller's current state: player mode with the track, queue length, segments and last progress, or actions mode when nothing plays. Call it when a screen starts while audio may already be playing (`MainScreen.on_mount`, `ChannelScreen.on_mount`) and after `play_audio` / `enqueue_audio` from a key or menu: a menu's callback can run while the modal is still `app.screen`, and the broadcast is not guaranteed to have landed.
- The `on_audio_*` and `on_player_state_updated` handlers apply the controller's broadcasts. The controller posts to every screen on the stack, so a screen under another screen keeps its bar current; there is no resume-time resync.
- `_refresh_queue_hint(entry)` hides the enqueue hint when the focused row is already playing or queued. `MainScreen` also calls it from its row-selected handler.

Needs `_detail()` and `_selected_entry()` from `DetailFocusMixin` and `ListNavMixin`.
