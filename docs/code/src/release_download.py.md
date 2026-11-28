# src/release_download.py

The installer's network side: `download` (retries, progress line, failure advice) and `github_latest_tag`. Split from `src/bootstrap.py`, which is its only caller. Stdlib only, for the same reason as the installer: it runs before pip.

## Invariants

- `download` writes `<dest>.tmp` and `os.replace()`s it after a size check against `Content-Length`. An interrupted download never overwrites a working binary.
- Release tags come from the GitHub API first (`GITHUB_TOKEN`, if set, is sent to `api.github.com` only), then from where `https://github.com/<owner>/<repo>/releases/latest` redirects (`.../releases/tag/<tag>`). The API allows 60 unauthenticated requests an hour per address, which CI runners and shared networks exhaust; the redirect is not limited that way.
- Corporate proxies that intercept HTTPS raise `CERTIFICATE_VERIFY_FAILED`. `_classify_download_error` maps that, timeouts and resets to targeted advice (`_ADVICE`). Certificate verification is never disabled here.
- `ssl` may be missing from a stripped Python, so its import is guarded.
