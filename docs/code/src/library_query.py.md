# src/library_query.py

Filter syntax for the Library tab and playlists: free words plus `key:value` tokens, as a pure parser and predicate so the list filter can call
it through `VideoListPanel.set_matcher` and other tabs keep plain `fuzzy.rank`.

- Tokens: `type:audio|video` (the forms a row exists in, `library.kinds`), `dur:<10m` / `dur:>1h30m` (also `90`, `1:30`, `1:02:03`), `by:name` (uploader or
  channel), `year:2024` (upload date), `pl:name` (playlist membership), `dl:yes|no` (file on disk).
- A token with a bad value, an unknown key or an empty value is not an error: it stays a free word. A double-quoted run is one word, also after `key:`;
  an unclosed quote runs to the end of the text.
- Free words must all match; fields are title, uploader and channel, tags, description (weights in `_FIELD_WEIGHTS`), scored by `fuzzy.score_tokens`.
  Results are ranked best first, ties keep list order; with only tokens the list order is kept.
- `pl:` needs `{video id: [playlist names]}`; `rank` takes a callable and calls it once, and only when the query has a `pl:` token.
  Checks receive a lookup bound to that one result (`_names_for`).
