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


def test_untrusted_ipc_dir_prints_one_plain_line_and_exits_one(monkeypatch, capsys, tmp_path):
    from src.config import Config

    cfg = Config(path=str(tmp_path / "config.yaml"))
    monkeypatch.setattr(sys, "argv", ["termtube"])
    monkeypatch.setattr("src.deps.check_dependencies", lambda: True)
    monkeypatch.setattr("src.config.Config", lambda *a, **k: cfg)
    monkeypatch.delitem(sys.modules, "src.tui.app", raising=False)

    import builtins

    real_import = builtins.__import__

    def deny(name, *args, **kwargs):
        if name == "src.tui.app":
            raise PermissionError(1, "is owned by another user", "/tmp/termtube-evil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny)
    with pytest.raises(SystemExit) as exit_info:
        main.main()
    err = capsys.readouterr().err
    assert exit_info.value.code == 1
    assert err.count("\n") == 1 and "ls -ld /tmp/termtube-evil" in err and "Traceback" not in err
