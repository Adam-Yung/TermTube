"""Thumbnail downloads: verified TLS by default, opt-in unverified retry, 2 MB cap, decode check."""

import io
import os
import ssl
import urllib.error
from unittest.mock import MagicMock, patch

from src import thumbnail_http
from src.config import Config
from src.ui import thumbnail

URL = "https://i.ytimg.com/vi/abc123def45/mqdefault.jpg"


def _response(body: bytes):
    resp = MagicMock()
    resp.read.side_effect = lambda n=-1: body if n < 0 else body[:n]
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.frombytes("RGB", (32, 32), os.urandom(32 * 32 * 3)).save(buf, "PNG")
    return buf.getvalue()


def test_ssl_failure_gives_up_by_default(tmp_path):
    dest = tmp_path / "t.jpg"
    with patch("urllib.request.urlopen", side_effect=ssl.SSLError("bad cert")) as opened:
        assert thumbnail_http.download_thumbnail(URL, str(dest)) is False
    assert opened.call_count == 1
    assert not dest.exists()


def test_insecure_opt_in_retries_unverified(tmp_path):
    dest = tmp_path / "t.jpg"
    calls = []

    def fake(req, timeout, context):
        calls.append(context.verify_mode)
        if context.verify_mode != ssl.CERT_NONE:
            raise ssl.SSLError("bad cert")
        return _response(b"x" * 500)

    with patch("urllib.request.urlopen", side_effect=fake):
        assert thumbnail_http.download_thumbnail(URL, str(dest), insecure=True) is True
    assert calls == [ssl.CERT_REQUIRED, ssl.CERT_NONE]


def test_url_error_about_certificate_also_gives_up(tmp_path):
    err = urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
    with patch("urllib.request.urlopen", side_effect=err) as opened:
        assert thumbnail_http.download_thumbnail(URL, str(tmp_path / "t.jpg")) is False
    assert opened.call_count == 1


def test_body_over_two_megabytes_is_refused(tmp_path):
    dest = tmp_path / "t.jpg"
    with patch("urllib.request.urlopen", return_value=_response(b"x" * (thumbnail_http._THUMB_MAX_BYTES + 5))):
        assert thumbnail_http.download_thumbnail(URL, str(dest)) is False
    assert not dest.exists()


def test_only_http_urls_are_fetched(tmp_path):
    with patch("urllib.request.urlopen") as opened:
        assert thumbnail_http.download_thumbnail("file:///etc/passwd", str(tmp_path / "t.jpg")) is False
    opened.assert_not_called()


def test_download_keeps_a_decodable_image(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "THUMB_DIR", tmp_path)
    with patch("urllib.request.urlopen", return_value=_response(_png())):
        path = thumbnail.download("abc123def45", URL)
    assert path == tmp_path / "abc123def45.jpg"
    assert path.exists()


def test_download_drops_bytes_that_are_not_an_image(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "THUMB_DIR", tmp_path)
    with patch("urllib.request.urlopen", return_value=_response(b"<html>captive portal</html>" * 10)):
        assert thumbnail.download("abc123def45", URL) is None
    assert not (tmp_path / "abc123def45.jpg").exists()


def test_insecure_thumbnails_config_is_strict(tmp_path):
    path = tmp_path / "config.yaml"
    assert Config(path=str(path)).insecure_thumbnails is False
    path.write_text("insecure_thumbnails: true\n", encoding="utf-8")
    assert Config(path=str(path)).insecure_thumbnails is True
    path.write_text("insecure_thumbnails: 'true'\n", encoding="utf-8")
    assert Config(path=str(path)).insecure_thumbnails is False


def test_a_refused_extractor_url_falls_back_to_the_plain_id_url(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail, "THUMB_DIR", tmp_path)
    tried = []

    def fake(url, dest, timeout=8, *, insecure=False):
        tried.append(url)
        if "sqp=" in url:
            return False
        from PIL import Image
        Image.new("RGB", (4, 4)).save(dest, "JPEG")
        return True

    monkeypatch.setattr(thumbnail_http, "download_thumbnail", fake)
    path = thumbnail.download("abc123def45", "https://i.ytimg.com/vi/abc123def45/hq720.jpg?sqp=x")
    assert path is not None and path.exists()
    assert tried == ["https://i.ytimg.com/vi/abc123def45/hq720.jpg?sqp=x", URL]


def test_the_keychain_certificates_join_the_verified_context(monkeypatch):
    monkeypatch.setattr(thumbnail_http, "_macos_keychain_pem", lambda: "not a certificate")
    ctx = thumbnail_http._ssl_context_verified()  # unparsable input is ignored, verification stays on
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert not ctx.verify_flags & getattr(ssl, "VERIFY_X509_STRICT", 0)
