"""Tests for src/history.py — local watch history."""

import json
import time

import pytest

from src import history


class TestAdd:
    def test_stores_entry(self, temp_history):
        history.add({"id": "vid1", "title": "First Video"})
        entries = history.all_entries()
        assert len(entries) == 1
        assert entries[0]["id"] == "vid1"
        assert entries[0]["title"] == "First Video"
        assert "_watched_at" in entries[0]

    def test_deduplicates_moves_to_front(self, temp_history):
        history.add({"id": "vid1", "title": "First"})
        history.add({"id": "vid2", "title": "Second"})
        history.add({"id": "vid1", "title": "First Again"})

        entries = history.all_entries()
        assert len(entries) == 2
        assert entries[0]["id"] == "vid1"
        assert entries[1]["id"] == "vid2"

    def test_ignores_entry_without_id(self, temp_history):
        history.add({"title": "No ID"})
        assert history.all_entries() == []


class TestMaxEntriesCap:
    def test_respects_cap(self, temp_history):
        seed = [{"id": f"old{i}", "_watched_at": i} for i in range(500)]
        temp_history.write_text(json.dumps(seed))

        history.add({"id": "newest", "title": "Newest"})

        entries = history.all_entries()
        assert len(entries) == 500
        assert entries[0]["id"] == "newest"


class TestGetAll:
    def test_returns_reverse_chronological(self, temp_history):
        history.add({"id": "old", "title": "Old"})
        history.add({"id": "mid", "title": "Mid"})
        history.add({"id": "new", "title": "New"})

        entries = history.all_entries()
        assert [e["id"] for e in entries] == ["new", "mid", "old"]


class TestPersistence:
    def test_survives_reload(self, temp_history):
        history.add({"id": "persist1", "title": "A"})
        history.add({"id": "persist2", "title": "B"})

        raw = json.loads(temp_history.read_text())
        assert len(raw) == 2
        assert raw[0]["id"] == "persist2"
        assert raw[1]["id"] == "persist1"
