"""Fetches a public thumbnail over HTTP(S), verifying TLS against the default bundle plus the macOS keychain."""

from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path

_THUMB_MAX_BYTES = 2 * 1024 * 1024


def download_thumbnail(url: str, dest: str, timeout: int = 8, *, insecure: bool = False) -> bool:
    """Fetch a thumbnail (http or https, at most 2 MB) to dest. True on success.

    A certificate failure is final unless ``insecure`` (config ``insecure_thumbnails``) allows one retry
    without verification, for MITM proxies on corporate networks. Never reuse that retry for anything but
    public CDN images.
    """
    import ssl
    import urllib.error
    import urllib.request

    if not url.lower().startswith(("https://", "http://")):
        return False
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    contexts = (_ssl_context_verified(), _ssl_context_unverified()) if insecure else (_ssl_context_verified(),)
    for ctx in contexts:
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read(_THUMB_MAX_BYTES + 1)
            if not 100 <= len(data) <= _THUMB_MAX_BYTES:
                return False
            Path(dest).write_bytes(data)
            return True
        except ssl.SSLError:
            continue
        except urllib.error.URLError as e:
            if "SSL" in str(e) or "certificate" in str(e).lower():
                continue
            return False
        except Exception:
            return False
    return False


@functools.lru_cache(maxsize=1)
def _macos_keychain_pem() -> str:
    """Certificates (public parts only) of the macOS keychains, as PEM; "" elsewhere or on any failure.

    Python builds that ship their own CA bundle (conda, python.org) do not know a company's TLS-inspection root,
    which macOS trusts through the keychain; without it every image host that is inspected fails verification.
    """
    if sys.platform != "darwin":
        return ""
    pems = []
    for extra in ([], ["/System/Library/Keychains/SystemRootCertificates.keychain"]):
        try:
            done = subprocess.run(
                ["/usr/bin/security", "find-certificate", "-a", "-p", *extra],
                capture_output=True, text=True, timeout=15, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        pems.append(done.stdout)
    return "\n".join(pems)


def _ssl_context_verified():
    import ssl
    ctx = ssl.create_default_context()
    pem = _macos_keychain_pem()
    if pem:
        try:
            ctx.load_verify_locations(cadata=pem)
        except ssl.SSLError:
            pass  # one unparsable certificate: keep the default bundle
        # Inspection roots often lack key identifiers Python 3.13 insists on; chain and host name are still checked.
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return ctx


def _ssl_context_unverified():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
