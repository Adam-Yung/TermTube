# src/feed_cache.py

The rules for cached id lists behind feeds and searches, split from `src/ytdlp.py`, its only caller. A cached list is served only when
enough of it is usable; a search extension is appended to the ids already stored, and nothing is stored when there is no list to append to.
