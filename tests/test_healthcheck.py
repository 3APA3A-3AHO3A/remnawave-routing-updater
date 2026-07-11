"""Tests for the liveness heartbeat and the Docker healthcheck entry point."""

import os

from routing_updater import healthcheck, runtime


def test_write_heartbeat_creates_file(tmp_path):
    hb = tmp_path / "output" / ".heartbeat"
    runtime.write_heartbeat(str(hb))
    assert hb.exists()
    assert hb.read_text().isdigit()


def test_is_healthy_fresh_and_stale(tmp_path, monkeypatch):
    hb = tmp_path / ".heartbeat"
    hb.write_text("1")
    monkeypatch.setattr(healthcheck, "HEARTBEAT_PATH", str(hb))
    monkeypatch.setattr(healthcheck, "MAX_AGE_SECONDS", 100)

    mtime = os.path.getmtime(str(hb))
    assert healthcheck.is_healthy(now=mtime + 50) is True     # within the window
    assert healthcheck.is_healthy(now=mtime + 500) is False   # gone stale


def test_is_healthy_missing_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr(healthcheck, "HEARTBEAT_PATH", str(tmp_path / "does-not-exist"))
    assert healthcheck.is_healthy() is False
