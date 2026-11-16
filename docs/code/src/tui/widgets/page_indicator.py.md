# src/tui/widgets/page_indicator.py

One-line footer under the video list: `◀  Page N / M  ▶`. `VideoListPanel` feeds it through `update_state` and re-posts its clicks.

An arrow is drawn only when that move is possible: `◀` needs a previous page, `▶` needs the next page to be held in memory (`next_ready`). A click on the left half posts `PrevPage`, on the right half `NextPage`, only when the arrow is active. `VideoListPanel` stops the message and posts `PageChangeRequested`, which `ListNavMixin` handles like the `h`/`l` keys.
