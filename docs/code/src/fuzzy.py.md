# src/fuzzy.py

The list filter's matcher: a pure function, no state, no dependency. `rank(entries, query)` splits the query on whitespace, folds case and (for non-ASCII text) accents, and keeps an entry only when every token occurs in the title or in `uploader`/`channel`. Order: prefix of the title (100), start of a word (60), anywhere (20); a hit in uploader/channel counts half; token scores add; ties keep the input order.

- Substring matching only, not subsequence: `abc` does not match `a-b-c`. A subsequence pass costs 10x on non-matching rows and ranks noise; revisit if users ask.
- `casefold` makes `STRASSE` find `Straße`. 10,000 rows rank in about 10 ms (`test_ten_thousand_rows_rank_quickly` allows 50 ms).
- Callers: `VideoListPanel._rebuild_filtered` on every keystroke and whenever pages arrive while a filter is active.
