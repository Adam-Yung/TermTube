"""Every modal opens inside the screen, centered, with nothing protruding, at the sizes in ``layout_harness``."""

import pytest

from src import playlist
from src.tests.tui.layout_harness import SIZES, SMALL_SIZE, Scenario, audit_scenario
from src.tui.audio_controller import AudioController
from src.tui.screens.channel_tab_modal import ChannelTabModal
from src.tui.screens.download_modal import DownloadModal
from src.tui.screens.download_picker_modal import DownloadPickerModal
from src.tui.screens.empty_feed_modal import EmptyFeedModal
from src.tui.screens.help_screen import HelpScreen
from src.tui.screens.image_warning_modal import ImageWarningModal
from src.tui.screens.name_modal import NameModal
from src.tui.screens.nav_modal import NavModal
from src.tui.screens.playlist_modal import PlaylistModal
from src.tui.screens.quality_modal import QualityModal
from src.tui.screens.queue_modal import QueueModal
from src.tui.screens.search_modal import SearchModal
from src.tui.screens.settings_modal import SettingsModal
from src.tui.screens.sort_modal import SortModal
from src.tui.screens.video_action_modal import VideoActionModal
from src.tui.screens.watch_modal import WatchModal
from src.tui.screens.ytdlp_update_modal import YtdlpUpdateModal

VIDEO = {
    "id": "abc123def45",
    "title": "A rather long video title that goes on and on to test how the dialog header copes with it",
    "uploader": "A Channel With A Long Name Indeed",
}


def _queue(app):
    app.audio._play_pending = True
    app.audio._entry = {"id": "AAAAAAAAAAA", "title": "Playing", "uploader": "U", "duration": 600}
    app.audio._queue = [{"id": f"Q{i:010d}", "title": f"Queued track number {i}", "duration": 90} for i in range(30)]


def _playlists(app):
    for i in range(30):
        playlist.create(f"Playlist number {i}", [VIDEO])


SCENARIOS = [
    Scenario("video-actions", lambda app: VideoActionModal(VIDEO)),
    Scenario("name", lambda app: NameModal("New playlist")),
    Scenario("playlist", lambda app: PlaylistModal(VIDEO), before=_playlists),
    Scenario("playlist-empty", lambda app: PlaylistModal(VIDEO)),
    Scenario("download-picker", lambda app: DownloadPickerModal(title=VIDEO["title"])),
    Scenario("quality-video", lambda app: QualityModal()),
    Scenario("quality-audio", lambda app: QualityModal(audio_only=True)),
    Scenario("sort", lambda app: SortModal()),
    Scenario("channel-tab", lambda app: ChannelTabModal()),
    Scenario("settings", lambda app: SettingsModal()),
    Scenario("search", lambda app: SearchModal()),
    Scenario("queue", lambda app: QueueModal(), before=_queue),
    Scenario("queue-empty", lambda app: QueueModal()),
    Scenario("nav", lambda app: NavModal()),
    Scenario("empty-feed", lambda app: EmptyFeedModal()),
    Scenario("ytdlp-update", lambda app: YtdlpUpdateModal("ERROR: " + "x" * 200)),
    Scenario("image-warning", lambda app: ImageWarningModal()),
    Scenario("download", lambda app: DownloadModal(VIDEO["id"], VIDEO)),
    Scenario("watch", lambda app: WatchModal(VIDEO), dialog="#watch-dialog"),
    Scenario("help", lambda app: HelpScreen(), dialog="#help-outer"),
]


@pytest.fixture
def quiet(app, temp_playlists, monkeypatch):
    """The app with Home's startup load and the thumbnail/focus workers silenced."""
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_focus", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.mixins.detail_focus.DetailFocusMixin._kick_thumb", lambda *a: None)
    monkeypatch.setattr("src.tui.screens.main_screen.MainScreen._show_empty_feed_modal", lambda *a, **k: None)
    monkeypatch.setattr(DownloadModal, "_start_download", lambda self: None)
    monkeypatch.setattr(WatchModal, "_launch_video", lambda self: None)
    monkeypatch.setattr(WatchModal, "_poll_mpv", lambda self: None)
    monkeypatch.setattr(AudioController, "_launch_worker", lambda *a, **k: None)
    return app


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
async def test_modal_layout(quiet, scenario):
    sizes = SIZES + ([SMALL_SIZE] if scenario.small else [])
    async with quiet.run_test(size=SIZES[0]) as pilot:
        problems = await audit_scenario(quiet, pilot, scenario, sizes)
    assert not problems, "\n".join(problems)
