"""Tests for src/config.py — configuration management."""


import yaml


class TestDefaultConfig:
    def test_default_values(self, tmp_path):
        from src.config import Config

        config_path = tmp_path / "config.yaml"
        cfg = Config(path=str(config_path))

        assert cfg["preferred_quality"] == "best"
        assert cfg["browser"] == "auto"
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
        config_path.write_text(yaml.dump({"preferred_quality": "720p"}), encoding="utf-8")

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
        , encoding="utf-8")

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.sponsorblock_enabled is False
        assert cfg.sponsorblock_auto_skip is False
        assert cfg.sponsorblock_categories == ["sponsor", "intro", "outro"]

class TestDirPaths:
    def test_video_dir(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        target = tmp_path / "MyVideos"
        config_path.write_text(yaml.dump({"video_dir": str(target)}), encoding="utf-8")

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.video_dir == target

    def test_audio_dir(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        target = tmp_path / "MyAudio"
        config_path.write_text(yaml.dump({"audio_dir": str(target)}), encoding="utf-8")

        from src.config import Config

        cfg = Config(path=str(config_path))
        assert cfg.audio_dir == target

    def test_default_dirs_under_home(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert "TermTube" in str(cfg.video_dir)
        assert "TermTube" in str(cfg.audio_dir)


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


def test_set_changes_memory_and_save_persists(tmp_path):
    from src.config import Config

    path = tmp_path / "config.yaml"
    config = Config(path=str(path))
    config.set("theme", "ocean")
    assert config.theme == "ocean"
    assert Config(path=str(path)).theme == "crimson"
    config.save()
    assert Config(path=str(path)).theme == "ocean"


def test_removed_thumbnail_formats_read_back_as_auto(tmp_path):
    from src.config import Config

    path = tmp_path / "config.yaml"
    path.write_text("thumbnail_format: sixel\n", encoding="utf-8")
    assert Config(path=str(path)).thumbnail_format == "auto"
    path.write_text("thumbnail_format: symbols\n", encoding="utf-8")
    assert Config(path=str(path)).thumbnail_format == "symbols"


class TestRowsPerPage:
    def test_default_and_clamp(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.rows_per_page == 20
        for raw, want in ((5, 10), (99, 50), (35, 35), ("30", 20), (True, 20), (None, 20)):
            cfg.set("rows_per_page", raw)
            assert cfg.rows_per_page == want


class TestPrefetchVideo:
    def test_only_a_literal_true_enables_it(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.prefetch_video_enabled is False
        for raw, want in ((True, True), ("true", False), (1, False), (False, False)):
            cfg.set("prefetch_video", raw)
            assert cfg.prefetch_video_enabled is want


class TestResolvedBrowser:
    def test_none_and_named_and_auto(self, tmp_path, monkeypatch):
        from src.config import Config

        monkeypatch.setattr("src.browsers.detect_installed_browsers", lambda: [{"name": "firefox", "label": "Firefox"}])
        cfg = Config(path=str(tmp_path / "config.yaml"))
        assert cfg.resolved_browser() == "firefox"
        cfg.set("browser", "chrome")
        assert cfg.resolved_browser() == "chrome"
        assert cfg.browser_cookie_args() == ["--cookies-from-browser", "chrome"]
        cfg.set("browser", "none")
        assert cfg.resolved_browser() is None and cfg.browser_cookie_args() == []

    def test_auto_with_nothing_installed(self, tmp_path, monkeypatch):
        from src.config import Config

        monkeypatch.setattr("src.browsers.detect_installed_browsers", lambda: [])
        assert Config(path=str(tmp_path / "config.yaml")).resolved_browser() is None
