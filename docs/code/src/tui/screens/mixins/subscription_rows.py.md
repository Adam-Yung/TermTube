# src/tui/screens/mixins/subscription_rows.py

Detail panel content for a channel row. The avatar (`ch_thumb`) draws into the shared detail panel, so `MainScreen._cancel_pending_focus_and_thumb` bumps `_avatar_session` as well. `ch_focus` fetches channel info only when the row lacks a description or a thumbnail URL, and its result is dropped if the cursor moved.
