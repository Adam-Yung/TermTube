# Decision log

Each file records decisions made during implementation, grouped by topic. Entries are append-only and dated, with the newest at the bottom. Each entry has a `## YYYY-MM[-DD] — title` heading and states what was decided and why. When a decision changes, add a new entry and mark the old one DEPRECATED or SUPERSEDED with a link to its replacement.

Topic files:
- [runtime-and-env.md](runtime-and-env.md): venv, yt-dlp as a library, bundled dependencies, update strategy, setup scripts.
- [playback.md](playback.md): mpv IPC, video suspend, mpv.net rejection, play-pending guard, SponsorBlock, start latency.
- [concurrency.md](concurrency.md): `@work` threads, HomeScreen worker topology, process registry and shutdown.
- [feeds-and-paging.md](feeds-and-paging.md): feed caching, LRU suppression, paged system, single fetch, performance hardening.
- [cookies-and-auth.md](cookies-and-auth.md): browser cookies, shared cookie jar, which calls get auth, stream URL pre-resolution, option sets.
- [thumbnails.md](thumbnails.md): textual-image, chafa settings and cache, DetailPanel thumbnail interface.
- [logging.md](logging.md): `--debug`, `--level`, stderr policy, TUI log handler.
- [config.md](config.md): config location, `--sync` symlink, fzf/gum removal.

An older entry can describe a design that a later entry replaced. Read a topic file to the bottom before relying on any entry.
