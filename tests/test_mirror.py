"""Tests for the geo mirror. The network is faked via monkeypatch; files go to tmp_path."""

from routing_updater import mirror


class FakeResp:
    def __init__(self, status, content=b"", etag=None):
        self.status_code = status
        self.content = content
        self.headers = {"ETag": etag} if etag else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_first_download_writes_file_and_etag(tmp_path, monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return FakeResp(200, b"DATA", etag='"abc"')

    monkeypatch.setattr(mirror.requests, "get", fake_get)

    changed = mirror.mirror_geo_files(
        geo_dir=str(tmp_path), sources={"geoip.dat": "http://x"}, timeout=5
    )

    assert changed is True
    assert (tmp_path / "geoip.dat").read_bytes() == b"DATA"
    assert (tmp_path / "geoip.dat.etag").read_text() == '"abc"'
    assert "If-None-Match" not in seen["headers"]  # nothing to send on first run


def test_unchanged_returns_false_and_sends_etag(tmp_path, monkeypatch):
    (tmp_path / "geoip.dat.etag").write_text('"abc"')
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return FakeResp(304)

    monkeypatch.setattr(mirror.requests, "get", fake_get)

    changed = mirror.mirror_geo_files(
        geo_dir=str(tmp_path), sources={"geoip.dat": "http://x"}, timeout=5
    )

    assert changed is False
    assert seen["headers"].get("If-None-Match") == '"abc"'


def test_one_failure_does_not_break_the_other(tmp_path, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        if "bad" in url:
            raise RuntimeError("boom")
        return FakeResp(200, b"OK", etag='"e"')

    monkeypatch.setattr(mirror.requests, "get", fake_get)

    changed = mirror.mirror_geo_files(
        geo_dir=str(tmp_path),
        sources={"geoip.dat": "http://good", "geosite.dat": "http://bad"},
        timeout=5,
    )

    assert changed is True
    assert (tmp_path / "geoip.dat").exists()
    assert not (tmp_path / "geosite.dat").exists()  # failed file left absent, not partial
