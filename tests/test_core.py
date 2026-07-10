"""Tests for the orchestration layer.

``apply_changes`` is tested directly (pure). ``update_routing`` is tested with a
fake client and monkeypatched template I/O — showing how the client boundary and
the I/O split make the orchestration testable without a network or real files.
"""

from routing_updater import core, templating

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": "incy://autorouting/onadd/https://sub.example/routing.json",
}


def test_apply_changes_sets_happ_field():
    data = {}
    summary = core.apply_changes(
        data, LINKS, enable_happ=True, enable_incy=False, incy_response_type="XRAY_BASE64"
    )
    assert data["happRouting"] == LINKS["happ_routing"]
    assert any("Happ" in s for s in summary)


def test_apply_changes_creates_incy_rule_when_missing():
    data = {"happRouting": "z"}
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    created = data["responseRules"]["rules"][0]
    assert created["name"] == "Incy"
    assert created["responseType"] == "XRAY_BASE64"


def test_apply_changes_keeps_existing_incy_response_type():
    data = {
        "responseRules": {
            "version": "1",
            "rules": [{"name": "Incy", "responseType": "XRAY_JSON"}],
        }
    }
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    assert data["responseRules"]["rules"][0]["responseType"] == "XRAY_JSON"


def test_apply_changes_skips_autorouting_on_created_rule_when_disabled():
    data = {}
    core.apply_changes(
        data,
        LINKS,
        enable_happ=False,
        enable_incy=True,
        incy_response_type="XRAY_BASE64",
        incy_autorouting=False,
    )
    rule = data["responseRules"]["rules"][0]
    keys = {h["key"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing"}


def test_apply_changes_skips_autorouting_on_existing_rule_when_disabled():
    data = {
        "responseRules": {
            "version": "1",
            "rules": [{"name": "Incy", "responseType": "XRAY_JSON"}],
        }
    }
    core.apply_changes(
        data,
        LINKS,
        enable_happ=False,
        enable_incy=True,
        incy_response_type="XRAY_BASE64",
        incy_autorouting=False,
    )
    headers = data["responseRules"]["rules"][0]["responseModifications"]["headers"]
    keys = {h["key"] for h in headers}
    assert keys == {"routing"}


def test_apply_changes_does_nothing_when_both_disabled():
    data = {"foo": "bar"}
    summary = core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=False, incy_response_type="XRAY_BASE64"
    )
    assert summary == []
    assert data == {"foo": "bar"}


class FakeClient:
    """Stands in for RemnawaveClient — same methods, no network."""

    def __init__(self, settings):
        self._settings = settings
        self.patched = None

    def get_settings(self):
        return self._settings

    def patch_settings(self, data):
        self.patched = data


def test_refresh_geo_trim_passes_config_dirs(monkeypatch):
    # Regression: refresh_geo must import GEO_DIR / GEO_CACHE_DIR (a NameError shipped once).
    monkeypatch.setattr(core, "GEO_MIRROR_ENABLED", True)
    monkeypatch.setattr(core, "GEO_TRIM_ENABLED", True)

    seen = {}
    monkeypatch.setattr(
        core.mirror, "mirror_geo_files", lambda geo_dir=None: seen.setdefault("mirror_dir", geo_dir)
    )
    monkeypatch.setattr(
        core.geobuild, "trim_all",
        lambda cache, out, site, ip: seen.update(cache=cache, out=out, site=site, ip=ip) or True,
    )
    monkeypatch.setattr(
        core.checksums, "write_sidecars", lambda directory: seen.setdefault("cksum_dir", directory)
    )

    template = {"DirectSites": ["geosite:private"], "DirectIp": ["geoip:private"]}
    assert core.refresh_geo(template) is True
    assert seen["mirror_dir"] == core.GEO_CACHE_DIR  # full downloaded into the private cache
    assert seen["cache"] == core.GEO_CACHE_DIR
    assert seen["out"] == core.GEO_DIR               # trimmed into the served dir
    assert seen["site"] == {"PRIVATE"}
    assert seen["ip"] == {"PRIVATE"}
    assert seen["cksum_dir"] == core.GEO_DIR         # checksum sidecars for the served files


def test_update_routing_pushes_patched_settings(monkeypatch):
    # Replace the file I/O so no real template or output file is needed.
    monkeypatch.setattr(templating, "load_template", lambda: {"Name": "T"})
    monkeypatch.setattr(templating, "save_output", lambda template: True)

    client = FakeClient({"happRouting": ""})
    core.update_routing(client)

    assert client.patched is not None
    assert client.patched["happRouting"].startswith("happ://routing/onadd/")
