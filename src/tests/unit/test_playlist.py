"""Tests for src/playlist.py — local playlist management."""

import pytest

from src import playlist


class TestListNames:
    def test_empty_initially(self, temp_playlists):
        assert playlist.list_names() == []


class TestCreate:
    def test_create_empty_playlist(self, temp_playlists):
        playlist.create("Favorites")
        assert "Favorites" in playlist.list_names()
        assert playlist.get_playlist("Favorites") == []

    def test_create_with_initial_videos(self, temp_playlists):
        playlist.create("Watch Later", ["vid1", "vid2"])
        assert playlist.get_playlist("Watch Later") == ["vid1", "vid2"]


class TestAddVideo:
    def test_add_to_existing_playlist(self, temp_playlists):
        playlist.create("Music")
        result = playlist.add_video("Music", "song1")
        assert result is True
        assert playlist.get_playlist("Music") == ["song1"]

    def test_add_creates_playlist_if_missing(self, temp_playlists):
        result = playlist.add_video("New List", "vid1")
        assert result is True
        assert "New List" in playlist.list_names()
        assert playlist.get_playlist("New List") == ["vid1"]

    def test_add_returns_false_if_duplicate(self, temp_playlists):
        playlist.create("Dupes", ["vid1"])
        result = playlist.add_video("Dupes", "vid1")
        assert result is False
        assert playlist.get_playlist("Dupes") == ["vid1"]


class TestRemoveVideo:
    def test_remove_existing_video(self, temp_playlists):
        playlist.create("Mix", ["a", "b", "c"])
        result = playlist.remove_video("Mix", "b")
        assert result is True
        assert playlist.get_playlist("Mix") == ["a", "c"]

    def test_remove_returns_false_if_not_found(self, temp_playlists):
        playlist.create("Mix", ["a"])
        assert playlist.remove_video("Mix", "z") is False

    def test_remove_returns_false_if_playlist_missing(self, temp_playlists):
        assert playlist.remove_video("NoSuch", "vid1") is False


class TestGetPlaylist:
    def test_returns_video_ids(self, temp_playlists):
        playlist.create("Coding", ["v1", "v2", "v3"])
        assert playlist.get_playlist("Coding") == ["v1", "v2", "v3"]

    def test_returns_empty_for_unknown_playlist(self, temp_playlists):
        assert playlist.get_playlist("ghost") == []


class TestDelete:
    def test_delete_existing(self, temp_playlists):
        playlist.create("Temp")
        result = playlist.delete("Temp")
        assert result is True
        assert "Temp" not in playlist.list_names()

    def test_delete_nonexistent_returns_false(self, temp_playlists):
        assert playlist.delete("nope") is False


class TestRename:
    def test_rename_preserves_order(self, temp_playlists):
        playlist.create("Alpha", ["v1", "v2"])
        playlist.create("Beta", ["v3"])
        playlist.rename("Alpha", "Gamma")

        names = playlist.list_names()
        assert names == ["Gamma", "Beta"]
        assert playlist.get_playlist("Gamma") == ["v1", "v2"]

    def test_rename_nonexistent_returns_false(self, temp_playlists):
        assert playlist.rename("ghost", "new") is False


class TestIsInPlaylist:
    def test_membership_true(self, temp_playlists):
        playlist.create("Fav", ["abc"])
        assert playlist.is_in_playlist("Fav", "abc") is True

    def test_membership_false(self, temp_playlists):
        playlist.create("Fav", ["abc"])
        assert playlist.is_in_playlist("Fav", "xyz") is False

    def test_membership_missing_playlist(self, temp_playlists):
        assert playlist.is_in_playlist("NoList", "vid") is False


class TestVideoPlaylists:
    def test_returns_all_containing_playlists(self, temp_playlists):
        playlist.create("A", ["vid1", "vid2"])
        playlist.create("B", ["vid2", "vid3"])
        playlist.create("C", ["vid3"])

        result = playlist.video_playlists("vid2")
        assert sorted(result) == ["A", "B"]

    def test_returns_empty_if_not_in_any(self, temp_playlists):
        playlist.create("X", ["other"])
        assert playlist.video_playlists("missing") == []


class TestMultiplePlaylistsCoexist:
    def test_operations_on_separate_playlists(self, temp_playlists):
        playlist.create("P1", ["a", "b"])
        playlist.create("P2", ["c", "d"])

        playlist.add_video("P1", "c")
        playlist.remove_video("P2", "c")

        assert playlist.get_playlist("P1") == ["a", "b", "c"]
        assert playlist.get_playlist("P2") == ["d"]
        assert playlist.list_names() == ["P1", "P2"]
