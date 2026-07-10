"""Tests for the dependency-free geo-database trimmer.

Fake .dat files are built with the module's own primitives, so the round-trip
(build -> parse -> trim -> parse) is exercised end to end without real 10-17 MB files.
"""

from routing_updater import geobuild


def _field(num, payload):
    """Encode one length-delimited field (wire type 2)."""
    return bytes([(num << 3) | 2]) + geobuild._encode_varint(len(payload)) + payload


def _entry(country_code, domain_payload=b"domain-bytes"):
    """Build a GeoSite/GeoIP entry: field 1 = country_code, field 2 = opaque payload."""
    return _field(1, country_code.encode()) + _field(2, domain_payload)


def _dat(*country_codes):
    """Build a full GeoSiteList/GeoIPList from the given category names."""
    return geobuild.serialize_entries([_entry(cc) for cc in country_codes])


def test_parse_roundtrips_and_reads_country_code():
    data = _dat("PRIVATE", "CATEGORY-RU", "GOOGLE")
    entries = geobuild.parse_entries(data)
    assert [cc for cc, _ in entries] == ["PRIVATE", "CATEGORY-RU", "GOOGLE"]
    # Re-serializing the same chunks reproduces the input exactly.
    assert geobuild.serialize_entries([chunk for _, chunk in entries]) == data


def test_trim_keeps_only_wanted_verbatim():
    original = geobuild.parse_entries(_dat("PRIVATE", "CATEGORY-RU", "GOOGLE"))
    data = geobuild.serialize_entries([c for _, c in original])

    new, found = geobuild.trim_bytes(data, {"PRIVATE", "CATEGORY-RU"})
    kept = geobuild.parse_entries(new)

    assert [cc for cc, _ in kept] == ["PRIVATE", "CATEGORY-RU"]
    assert found == {"PRIVATE", "CATEGORY-RU", "GOOGLE"}
    # kept entries are byte-for-byte identical to the originals (domains preserved)
    by_cc = {cc: chunk for cc, chunk in original}
    for cc, chunk in kept:
        assert chunk == by_cc[cc]


def test_trim_is_case_insensitive():
    data = _dat("Category-RU")
    new, _ = geobuild.trim_bytes(data, {"CATEGORY-RU"})
    assert [cc for cc, _ in geobuild.parse_entries(new)] == ["Category-RU"]


def test_categories_from_template():
    template = {
        "DirectSites": ["geosite:private", "GeoSite:Category-RU@ads", "domain:x.com", "x.org"],
        "ProxySites": ["geosite:google"],
        "BlockSites": [],
        "DirectIp": ["geoip:private", "1.2.3.0/24"],
        "ProxyIp": ["geoip:ru"],
        "BlockIp": [],
    }
    site, ip = geobuild.categories_from_template(template)
    assert site == {"PRIVATE", "CATEGORY-RU", "GOOGLE"}
    assert ip == {"PRIVATE", "RU"}


def test_trim_all_writes_and_is_idempotent(tmp_path):
    cache = tmp_path / "cache"
    out = tmp_path / "out"
    cache.mkdir()
    (cache / "geosite.dat").write_bytes(_dat("PRIVATE", "CATEGORY-RU", "GOOGLE"))
    (cache / "geoip.dat").write_bytes(_dat("PRIVATE", "RU", "CN"))

    changed = geobuild.trim_all(str(cache), str(out), {"PRIVATE", "CATEGORY-RU"}, {"PRIVATE"})
    assert changed is True

    site = geobuild.parse_entries((out / "geosite.dat").read_bytes())
    ip = geobuild.parse_entries((out / "geoip.dat").read_bytes())
    assert {cc for cc, _ in site} == {"PRIVATE", "CATEGORY-RU"}
    assert {cc for cc, _ in ip} == {"PRIVATE"}

    # Second run with identical inputs must not rewrite anything.
    assert geobuild.trim_all(str(cache), str(out), {"PRIVATE", "CATEGORY-RU"}, {"PRIVATE"}) is False
