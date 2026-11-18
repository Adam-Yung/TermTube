"""Tests for src/config.py — configuration management."""


import pytest
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


class TestReloadResetAndDottedKeys:
    def test_dotted_set_get_and_reset(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        cfg.set("sponsorblock.enabled", False)
        cfg.set("cache_ttl.home", 120)
        assert cfg.sponsorblock_enabled is False and cfg.get("cache_ttl.home") == 120 and cfg.cache_ttl("home") == 120
        cfg.reset("sponsorblock.enabled")
        cfg.reset("cache_ttl.home")
        assert cfg.sponsorblock_enabled is True and cfg.cache_ttl("home") == 3600
        cfg.set("history_max", 80)
        cfg.reset("history_max")
        assert cfg.history_max == 500

    def test_reset_copies_a_list_default(self, tmp_path):
        from src.config import DEFAULT_CONFIG, Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        cfg.reset("sponsorblock.categories")
        cfg.sponsorblock_categories.append("intro")
        assert DEFAULT_CONFIG["sponsorblock"]["categories"] == ["sponsor", "selfpromo"]

    def test_reload_replaces_settings_and_keeps_the_ttl_dict_identity(self, tmp_path):
        from src.config import Config

        path = tmp_path / "config.yaml"
        cfg = Config(path=str(path))
        ttl = cfg.get("cache_ttl")
        cfg.set("theme", "amber")
        path.write_text(yaml.dump({"theme": "ocean", "extra": 1, "cache_ttl": {"home": 5}}), encoding="utf-8")
        assert cfg.reload() is None
        assert cfg.theme == "ocean" and cfg.get("extra") == 1
        assert cfg.get("cache_ttl") is ttl and ttl["home"] == 5 and ttl["search"] == 1800

    def test_reload_drops_a_key_removed_from_the_file(self, tmp_path):
        from src.config import Config

        path = tmp_path / "config.yaml"
        cfg = Config(path=str(path))
        cfg.set("theme", "amber")
        path.write_text("{}\n", encoding="utf-8")
        assert cfg.reload() is None and cfg.theme == "crimson"

    @pytest.mark.parametrize("text", ["theme: [unclosed\n  - : :", "- a\n- b\n"])
    def test_a_bad_file_is_reported_and_memory_is_kept(self, tmp_path, text):
        from src.config import Config

        path = tmp_path / "config.yaml"
        cfg = Config(path=str(path))
        cfg.set("theme", "amber")
        path.write_text(text, encoding="utf-8")
        error = cfg.reload()
        assert error and "\n" not in error
        assert cfg.theme == "amber"

    def test_reload_of_a_missing_file_is_an_error(self, tmp_path):
        from src.config import Config

        cfg = Config(path=str(tmp_path / "config.yaml"))
        cfg.path.unlink()
        assert cfg.reload() == "the file does not exist"

    def test_save_reports_failure(self, tmp_path):
        from src.config import Config

        path = tmp_path / "config.yaml"
        cfg = Config(path=str(path))
        assert cfg.save() is True
        path.write_text("a: [unclosed", encoding="utf-8")
        assert cfg.save() is False

    def test_a_non_dict_section_keeps_the_defaults(self, tmp_path):
        from src.config import Config

        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"cache_ttl": 5, "sponsorblock": "x"}), encoding="utf-8")
        cfg = Config(path=str(path))
        assert cfg.cache_ttl("home") == 3600 and cfg.sponsorblock_enabled is True
