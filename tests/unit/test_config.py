"""Tests for src/config.py — configuration management."""

from pathlib import Path

import pytest
import yaml


class TestDefaultConfig:
    def test_default_values(self, tmp_path):
        from src.config import Config, DEFAULT_CONFIG

        config_path = tmp_path / "config.yaml"
        cfg = Config(path=str(config_path))

        assert cfg["preferred_quality"] == "best"
        assert cfg["preferred_player"] == "mpv"
        assert cfg["browser"] == "chrome"
        assert cfg["thumbnail_cols"] == 38
        assert cfg["thumbnail_rows"] == 20
        assert cfg["theme"] == "crimson"

    def test_creates_config_file_if_missing(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        assert not config_path.exists()

        from src.config import Config
        Config(path=str(config_path))

        assert config_path.exists()


class TestPreferredQuality:
    def test_default_value(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.preferred_quality == "best"

    def test_custom_value(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"preferred_quality": "720p"}))

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.preferred_quality == "720p"


class TestSponsorblock:
    def test_enabled_default(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.sponsorblock_enabled is True

    def test_auto_skip_default(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.sponsorblock_auto_skip is True

    def test_categories_default(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.sponsorblock_categories == ["sponsor", "selfpromo"]

    def test_custom_sponsorblock(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({
                "sponsorblock": {
                    "enabled": False,
                    "auto_skip": False,
                    "categories": ["sponsor", "intro", "outro"],
                }
            })
        )

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.sponsorblock_enabled is False
        assert cfg.sponsorblock_auto_skip is False
        assert cfg.sponsorblock_categories == ["sponsor", "intro", "outro"]


class TestCookieArgs:
    def test_cookie_file_returns_cookies_flag(self, tmp_path):
        cookies_path = tmp_path / "cookies.txt"
        cookies_path.write_text("# Netscape cookies file")

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"cookies_file": str(cookies_path), "browser": "firefox"})
        )

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.cookie_args() == ["--cookies", str(cookies_path)]

    def test_missing_cookie_file_returns_empty(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"cookies_file": str(tmp_path / "nonexistent.txt"), "browser": "firefox"})
        )

        from src.config import Config

        cfg = Config(path=str(config_path))
        # No file on disk → no flags (browser is never used at runtime)
        assert cfg.cookie_args() == []

    def test_empty_when_no_source(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"cookies_file": "", "browser": ""}))

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.cookie_args() == []


class TestDirPaths:
    def test_video_dir(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        target = tmp_path / "MyVideos"
        config_path.write_text(yaml.dump({"video_dir": str(target)}))

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.video_dir == target

    def test_audio_dir(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        target = tmp_path / "MyAudio"
        config_path.write_text(yaml.dump({"audio_dir": str(target)}))

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.audio_dir == target

    def test_default_dirs_under_home(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert "TermTube" in str(cfg.video_dir)
        assert "TermTube" in str(cfg.audio_dir)


class TestAutoUpdate:
    def test_default_is_true(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.auto_update is True

    def test_can_be_disabled(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"auto_update": False}))

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.auto_update is False

    def test_persists_after_save(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        from src.config import Config

        cfg = Config(path=str(config_path))
        cfg._data["auto_update"] = False
        cfg.save()

        cfg2 = Config(path=str(config_path))
        assert cfg2.auto_update is False


class TestSaveAndReload:
    def test_save_persists_changes(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        from src.config import Config

        cfg = Config(path=str(config_path))
        cfg._data["preferred_quality"] = "1080p"
        cfg._data["theme"] = "ocean"
        cfg.save()

        cfg2 = Config(path=str(config_path))
        assert cfg2.preferred_quality == "1080p"
        assert cfg2.theme == "ocean"

    def test_save_preserves_cache_ttl(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        from src.config import Config

        cfg = Config(path=str(config_path))
        cfg._data["cache_ttl"]["home"] = 7200
        cfg.save()

        cfg2 = Config(path=str(config_path))
        assert cfg2.cache_ttl("home") == 7200

    def test_save_preserves_sponsorblock(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        from src.config import Config

        cfg = Config(path=str(config_path))
        cfg._data["sponsorblock"]["enabled"] = False
        cfg.save()

        cfg2 = Config(path=str(config_path))
        assert cfg2.sponsorblock_enabled is False
