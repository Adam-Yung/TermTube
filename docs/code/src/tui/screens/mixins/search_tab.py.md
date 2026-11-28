# src/tui/screens/mixins/search_tab.py

The Search tab and the `s` key's two meanings (search order; local history order). State is created by `_init_search_tab`; `main_screen.py.md` describes the behaviour.

Cancelling the search dialog must not touch `tabs.active`: re-activating the current tab reloads its list.
