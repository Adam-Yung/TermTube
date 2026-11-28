"""The mpv command line of the foreground video player."""

from __future__ import annotations

from collections.abc import Callable

from src import player as player_mod


def build_command(
    exe: str,
    *,
    input_conf: str,
    socket_path: str,
    title: str,
    urls: list[str] | None,
    page_url: str,
    fmt: str,
    cookie_args: list[str],
    start: float | None = None,
) -> list[str]:
    """Play the resolved ``urls`` (video, or video and audio) directly; without them mpv resolves ``page_url``."""
    cmd = [
        exe,
        f"--input-conf={input_conf}",
        f"--input-ipc-server={socket_path}",
        "--no-terminal",
        "--really-quiet",
        "--msg-level=all=no",
        "--cache=yes",
        "--demuxer-max-bytes=150M",
        *player_mod.start_args(start),
    ]
    if title:
        cmd += [f"--title={title}", f"--force-media-title={title}"]
    if urls:
        cmd += ["--no-ytdl", *player_mod.source_args(urls[0])]
        if len(urls) == 2:
            cmd.append(f"--audio-file={urls[1]}")
        return cmd + ["--", urls[0]]
    cmd.append(f"--ytdl-format={fmt}")
    raw = player_mod.cookie_args_to_ytdl_raw(cookie_args)
    if raw:
        cmd.append(f"--ytdl-raw-options={raw}")
    return cmd + ["--", page_url]


class VideoCommand:
    """The command for each launch attempt: a retry asks ``refresh`` for new URLs and keeps the old ones without."""

    def __init__(
        self,
        build: Callable[[list[str] | None], list[str]],
        urls: list[str] | None,
        refresh: Callable[[], list[str] | None] | None,
    ) -> None:
        self._build = build
        self._urls = urls
        self._refresh = refresh

    def __call__(self, attempt: int) -> list[str]:
        if attempt > 1 and self._refresh:
            self._urls = self._refresh() or self._urls
        return self._build(self._urls)
