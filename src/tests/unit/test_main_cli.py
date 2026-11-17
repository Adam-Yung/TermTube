"""Tests for the command-line entry points in src/main.py."""

import sys

import pytest

from src import history, main


def test_clear_history_erases_and_exits_zero(temp_history, monkeypatch, capsys):
    history.add({"id": "a"})
    monkeypatch.setattr(sys, "argv", ["termtube", "--clear-history"])
    with pytest.raises(SystemExit) as exit_info:
        main.main()
    assert exit_info.value.code == 0
    assert history.all_entries() == []
    assert "cleared" in capsys.readouterr().out


def test_help_lists_clear_history(capsys):
    main._print_help()
    assert "--clear-history" in capsys.readouterr().out
