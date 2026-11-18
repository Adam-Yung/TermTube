from __future__ import annotations

import random

from src import library, playlist
from src.entries import Entry
from src.tui.fmt import escape_markup
from src.tui.screens.mixins.library_rail import PLAYLIST_VIEW as _PLAYLIST_TAB
from src.tui.screens.mixins.library_rail import tab_of
from src.tui.screens.mixins.list_tools import Removal
from src.tui.screens.name_modal import NameModal

_UNKNOWN_TITLE = "Unknown video"


def playlist_row(pl: dict) -> Entry:
    """A playlist as a row: what the delete question and the rename dialog read."""
    count = len(pl["items"])
    return {
        "id": f"__playlist__{pl['id']}",
        "title": pl["name"],
        "uploader": f"{count} video{'s' if count != 1 else ''}",
        "_playlist_id": pl["id"],
        "_playlist_name": pl["name"],
    }


def item_entries(pid: str, cache=None, config=None) -> list[Entry]:
    """The playlist's videos as list rows. A migrated item without a title is filled in from the cache once.

    With ``config`` each row carries its download state from the Library index (see `library.attach_local`).
    """
    record = playlist.get(pid)
    if record is None:
        return []
    if cache is not None and any(not i.get("title") for i in record["items"]):
        bare = [i["id"] for i in record["items"] if not i.get("title")]
        found = [{**raw, "id": vid} for vid in bare if (raw := cache.get_video_raw(vid))]
        if found and playlist.refresh_items(found):
            record = playlist.get(pid) or record
    rows = [{**i, "title": i.get("title") or _UNKNOWN_TITLE} for i in record["items"]]
    if config is None:
        return rows
    return library.attach_local(rows, library.all_entries(config.video_dir, config.audio_dir))


def _sync(app, ids, entries=()) -> None:
    if hasattr(app, "cache"):
        playlist.sync_pins(app.cache, ids, entries)


def _delete_question(targets: list[Entry]) -> tuple[str, dict[str, str]]:
    if len(targets) == 1:
        name = escape_markup(targets[0].get("_playlist_name", ""))
        count = targets[0].get("uploader", "")
        what = f'Delete playlist "{name}" ({count})?'
    else:
        what = f"Delete {len(targets)} playlists?"
    return f"[bold]{what} The videos stay on disk.[/bold]   [bold]y[/bold] / [dim]N[/dim]", {"y": ""}


class PlaylistToolsMixin:
    """Playlist management on the Library tab: new, rename, delete, reorder, play-all. Needs ListToolsMixin's screen.

    With the rail focused the target is the playlist under its cursor; otherwise it is the playlist the list shows.
    Needs `LibraryRailMixin` (`_rail_focused`, `_rail_playlist`, `_select_collection`, `_collection_entries`).
    """

    def _playlist_id(self) -> str | None:
        """The shown playlist's id, or None on any other view."""
        tab = self._current_tab
        return tab.removeprefix(_PLAYLIST_TAB) if tab.startswith(_PLAYLIST_TAB) else None

    def _target_playlist(self) -> str | None:
        if self._rail_focused():
            record = self._rail_playlist()
            return record["id"] if record else None
        return self._playlist_id()

    def _removal_key(self) -> str:
        return "playlists" if self._rail_focused() else super()._removal_key()

    def _delete_targets(self) -> list[Entry]:
        if not self._rail_focused():
            return super()._delete_targets()
        record = self._rail_playlist()
        return [playlist_row(record)] if record else []

    def _playlist_removals(self) -> dict[str, Removal]:
        """`D` handlers: on the rail, delete the playlist under the cursor; in a playlist, remove items only."""
        out = {"playlists": self._playlists_removal()}
        for pl in playlist.list_playlists():
            out[_PLAYLIST_TAB + pl["id"]] = self._items_removal(pl["id"])
        return out

    def _playlists_removal(self) -> Removal:
        def remove(targets: list[Entry], _choice: str) -> list[Entry]:
            gone = [(t, playlist.delete(t["_playlist_id"])) for t in targets if t.get("_playlist_id")]
            _sync(self.app, {i["id"] for _, rec in gone if rec for i in rec["items"]})
            return [{**t, "_record": rec} for t, rec in gone if rec]

        def restore(records: list[Entry]) -> None:
            for rec in (r["_record"] for r in records):
                if playlist.restore(rec):
                    _sync(self.app, {i["id"] for i in rec["items"]}, [])

        return Removal(
            remove=remove, restore=restore, reload=lambda: self._collection_entries(self._current_tab),
            noun="playlist", ask=_delete_question, label="Playlists",
        )

    def _items_removal(self, pid: str) -> Removal:
        def remove(targets: list[Entry], _choice: str) -> list[Entry]:
            removed = playlist.remove_items(pid, [t["id"] for t in targets])
            _sync(self.app, [i["id"] for i in removed])
            return removed

        def restore(records: list[Entry]) -> None:
            playlist.restore_items(pid, records)
            _sync(self.app, [r["id"] for r in records], records)

        return Removal(
            remove=remove, restore=restore, reload=lambda: self._collection_entries(_PLAYLIST_TAB + pid),
            noun="video", label="the playlist",
        )

    def action_playlist_new(self) -> None:
        if tab_of(self._current_tab) != "library":
            self._hint("Open the Library tab (F5) to create a playlist.", "information")
            return

        def done(name: str | None) -> None:
            if not name:
                return
            record = playlist.create(name)
            if record is None:
                self._hint(f'Playlist "{name}" already exists.')
                return
            self._select_collection(_PLAYLIST_TAB + record["id"], focus_list=not self._rail_focused())

        self.app.push_screen(NameModal("New playlist"), done)

    def action_playlist_rename(self) -> None:
        pid = self._target_playlist()
        record = playlist.get(pid) if pid else None
        if record is None:
            self._hint("Select a playlist to rename.", "information")
            return

        def done(name: str | None) -> None:
            if not name or name == record["name"]:
                return
            if not playlist.rename(record["id"], name):
                self._hint(f'Playlist "{name}" already exists.')
                return
            self._refresh_rail()
            if self._playlist_id() == record["id"]:
                self._list().set_breadcrumb(f"🎵 {name}")

        self.app.push_screen(NameModal("Rename playlist", record["name"]), done)

    def action_playlist_move_down(self) -> None:
        self._move_item(1)

    def action_playlist_move_up(self) -> None:
        self._move_item(-1)

    def _move_item(self, step: int) -> None:
        pid, entry = self._playlist_id(), self._selected_entry()
        if pid is None:
            self._hint("Open a playlist to reorder its videos.", "information")
        elif self._list().filter_active:
            self._hint("Clear the filter (f, Esc) before moving videos.")
        elif entry is not None:
            record = playlist.get(pid) or {"items": []}
            at = next((i for i, item in enumerate(record["items"]) if item["id"] == entry.get("id")), None)
            if at is None or not playlist.move_item(pid, entry["id"], at + step):
                self._hint("Already at the end of the playlist." if step > 0 else "Already at the top of the playlist.",
                           "information")
                return
            self._list().replace_entries(self._collection_entries(_PLAYLIST_TAB + pid), focus_id=entry["id"])

    def _playlist_tracks(self) -> list[Entry]:
        pid = self._target_playlist()
        if pid is None:
            self._hint("Open a playlist (or highlight one in the rail) first.", "information")
            return []
        tracks = self._collection_entries(_PLAYLIST_TAB + pid)
        if not tracks:
            self._hint("This playlist is empty.", "information")
        return tracks

    def action_playlist_play(self) -> None:
        self._play_tracks(self._playlist_tracks(), shuffle=False)

    def action_playlist_shuffle(self) -> None:
        self._play_tracks(self._playlist_tracks(), shuffle=True)

    def action_playlist_enqueue(self) -> None:
        tracks = self._playlist_tracks()
        if tracks:
            if self.app.audio.enqueue_many(tracks) == 0:
                self._hint("Everything is already queued.", "information")
            self._sync_player_bar()

    def _play_tracks(self, tracks: list[Entry], *, shuffle: bool) -> None:
        if tracks:
            if shuffle:
                tracks = random.sample(tracks, len(tracks))
            self.app.audio.play_many(tracks)
            self._sync_player_bar()
