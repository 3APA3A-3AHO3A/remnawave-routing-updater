"""Tests for the checksum sidecar writer."""

import hashlib

from routing_updater import checksums


def test_sidecars_have_gnu_sha256sum_format(tmp_path):
    data = b"hello geo database"
    (tmp_path / "geoip.dat").write_bytes(data)

    checksums.write_sidecars(str(tmp_path), names=("geoip.dat",))

    expected = f"{hashlib.sha256(data).hexdigest()}  geoip.dat\n"
    assert (tmp_path / "geoip.dat.sha256").read_text() == expected
    assert (tmp_path / "geoip.dat.sha256sum").read_text() == expected


def test_sidecars_are_idempotent(tmp_path):
    (tmp_path / "geoip.dat").write_bytes(b"x")
    checksums.write_sidecars(str(tmp_path), names=("geoip.dat",))
    sidecar = tmp_path / "geoip.dat.sha256"
    mtime = sidecar.stat().st_mtime_ns

    checksums.write_sidecars(str(tmp_path), names=("geoip.dat",))
    assert sidecar.stat().st_mtime_ns == mtime  # unchanged content -> not rewritten


def test_missing_database_is_skipped(tmp_path):
    checksums.write_sidecars(str(tmp_path), names=("nope.dat",))
    assert not (tmp_path / "nope.dat.sha256").exists()
