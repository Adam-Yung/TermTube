"""Local thumbnails and details with the real managed ffmpeg and ffprobe, on files generated here (lavfi)."""

import subprocess

import pytest
from PIL import Image

from src import local_files, local_media

FFMPEG = local_media._tool("ffmpeg")
pytestmark = pytest.mark.skipif(not (FFMPEG and local_media._tool("ffprobe")), reason="managed ffmpeg is not installed")


def make(path, *args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args, str(path)], check=True, timeout=60)
    return next(e for e in local_files.list_folder(path.parent).entries if e.get("_local_path") == str(path))


@pytest.fixture(autouse=True)
def fresh_cache():
    local_media.clear_cache()


def test_video_frame_and_details(tmp_path):
    entry = make(tmp_path / "-clip: https:x.mp4", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=10",
                 "-c:v", "mpeg4")
    fields = local_media.details(entry)
    assert fields["duration"] == 5 and "320×240" in fields["description"]
    dest = local_media.thumbnail(entry, tmp_path / "thumbs" / "c.jpg")
    with Image.open(dest) as img:
        assert img.width == 480


def test_file_shorter_than_3_s_still_gets_a_frame(tmp_path):
    entry = make(tmp_path / "short.mp4", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                 "-c:v", "mpeg4")
    assert local_media.thumbnail(entry, tmp_path / "s.jpg")


def test_audio_cover_art_is_the_thumbnail(tmp_path):
    entry = make(tmp_path / "song.m4a", "-f", "lavfi", "-i", "sine=duration=2", "-f", "lavfi", "-i",
                 "color=red:size=64x64:duration=1", "-map", "0:a", "-map", "1:v", "-c:a", "aac", "-c:v", "mjpeg",
                 "-frames:v", "1", "-disposition:v:0", "attached_pic")
    dest = local_media.thumbnail(entry, tmp_path / "a.jpg")
    with Image.open(dest) as img:
        red, green, blue = img.convert("RGB").getpixel((img.width // 2, img.height // 2))
    assert red > 200 and green < 60 and blue < 60


def test_audio_without_cover_has_details_but_no_thumbnail(tmp_path):
    entry = make(tmp_path / "plain.mp3", "-f", "lavfi", "-i", "sine=duration=2", "-c:a", "libmp3lame")
    assert "Audio: mp3" in local_media.details(entry)["description"]
    assert local_media.thumbnail(entry, tmp_path / "p.jpg") is None
