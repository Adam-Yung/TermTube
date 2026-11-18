# Accounts, cookies and privacy

TermTube has no login of its own and no telemetry. It can borrow the YouTube session of a browser you already use, for exactly these account feeds: Home, the subscription list, YouTube watch history and Watch Later (the last two are read-only views in the History tab).

## What needs an account

| Feature | Account? | Why |
|---|---|---|
| **Home feed** | yes | YouTube personalises it; without a session it is generic or empty |
| **Subscription list** (the channels you follow) | yes | it is your data |
| **YouTube history** and **Watch Later** (History tab, `Y` switches source) | yes | it is your data; read-only here |
| Search, channel pages, playlists, video details | no | public data, fetched anonymously |
| Stream URLs for playback, downloads | no, deliberately | requests carrying account cookies got YouTube's degraded "tv downgraded player" answer (5 poor formats instead of 37+) |
| Local library, history, local playlists | no | files on your machine |

## The `browser` setting

`browser` in `config.yaml` (also Settings `,` → Browser) says where the session comes from:

- `auto` (default): the first installed browser found. On macOS the order starts with **Firefox**, because Chrome and Brave protect their cookies with
  the keychain and prompt for access, and Safari's store is sandboxed.
- a browser name (`firefox`, `chrome`, `brave`, `edge`, and the others yt-dlp can read cookies from): use that one.
- `none` (or empty): anonymous mode; nothing is ever read from a browser. Home and Subscriptions then show generic or no content, and the YouTube and Watch Later sources say they need a signed-in browser.

The Settings picker lists detected browsers first, then supported but missing ones labelled "(not found)", and shows whether cookies will be used (the Account section has a read-only "In use" line naming the browser `auto` resolved to, or saying there are no cookies). The picker also offers `none`.
You must be signed in to YouTube in that browser. `termtube --browser-help` prints the short version.

## How the cookies are handled

- **Prewarmed.** After the first paint a background thread reads the cookies (`cookie_prewarm`, default true; Settings, Account section), so Home usually finds a warm jar. It never runs when `browser` is `none` or nothing resolves, nor twice. Set `cookie_prewarm: false` to read only on demand. On demand, the browser is read the first time one of the account feeds needs the account, which takes
  5 to 15 s on a cold profile. A session that only searches, plays and browses channels never touches the browser profile.
- **Narrow.** Only `youtube.com` and `google.com` cookies are kept (subdomains included); everything else is dropped immediately.
- **In memory only.** Never written to disk, never copied, never in a log.
- **Only where needed.** Attached to the yt-dlp calls for the account feeds above (a test pins the list of call sites). Never sent to the InnerTube web API, to stream resolution, to downloads or to SponsorBlock.
- **Renewed on failure only.** The cookie jar is kept until an authentication error (`sign in`, `login required`, HTTP 401/403 in yt-dlp's text)
  invalidates it; the call is then retried once with a fresh read. There is no timer: switching accounts in the browser takes effect after such an
  error or a restart.
- Legacy `cookies_file` settings are ignored (dropped from memory on load); there is no cookies.txt mode.

mpv gets the browser setting separately (`--ytdl-raw-options=cookies-from-browser=...`) only for the rare fallback where mpv itself resolves a page URL.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Home is empty | choose a browser that is signed in (Settings `,`), or check it is not `none` |
| The first Home load waits several seconds | that is the one-time cookie read |
| Keychain prompt on macOS | expected for Chrome/Brave; use Firefox or `none` |
| `cookie extraction failed` in the debug log | the profile is locked or the keychain was denied: close the browser or pick another one |

Design record: `docs/decisions/cookies-and-auth.md`; code: `docs/code/src/cookies.py.md`, `docs/code/src/browsers.py.md`, and the cookie policy table in
`docs/code/src/ytdlp.py.md`.
