# src/strings.py

The lookup for every user-facing string. `strings.json` (next to it, grouped by the module that uses each string) is the only place UI
wording lives: notices, modal titles and hints, panel labels, help rows, settings labels, error messages shown to the user.

- `text("area.key", **values)` flattens the nested JSON to dotted keys once (cached), then fills `{name}` placeholders with `str.format`.
  With no values it does not format, so a string used that way keeps single braces (`{ }`); a string used with values must double them.
- A missing key raises `KeyError`; tests catch typos that way.
- Some modules call `text()` at import time (keymap labels, tab names, settings fields), so the JSON must always ship with `src/`.
- Keys built from an f-string (`list_tools.noun_{n}`, `action_bar.key_*`) look unused in a grep; search the prefix.
- Left in code on purpose: key glyphs, CSS ids, log lines and developer exception text.
