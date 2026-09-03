"""Tests for the orchestration layer.

``apply_changes`` is tested directly (pure). ``update_routing`` is tested with a
fake client and monkeypatched template I/O — showing how the client boundary and
the I/O split make the orchestration testable without a network or real files.
"""

from routing_updater import core, remnawave, templating

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": "incy://autorouting/onadd/https://sub.example/routing.json",
}

UUID = "0f2b0b3e-0000-4000-8000-000000000000"


def settings(**overrides):
    """A minimal subscription-settings payload, as the panel would return it."""
    base = {"uuid": UUID, "responseRules": None}
    base.update(overrides)
    return base


def headers_of(data, index=0):
    rule = data["responseRules"]["rules"][index]
    return {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}


# --------------------------------------------------------------------------- #
# apply_changes
# --------------------------------------------------------------------------- #


def test_apply_changes_never_writes_happ_routing_field():
    # The dedicated field is gone in 3.x and was a duplicate source of truth in 2.x.
    data = settings(happRouting="stale-value")
    core.apply_changes(data, LINKS, enable_happ=True, enable_incy=False)
    assert data["happRouting"] == "stale-value"  # left exactly as found


def test_apply_changes_creates_happ_rule_when_missing():
    data = settings()
    summary = core.apply_changes(
        data, LINKS, enable_happ=True, enable_incy=False, happ_response_type="XRAY_BASE64"
    )
    created = data["responseRules"]["rules"][0]
    assert created["name"] == "Happ"
    assert created["responseType"] == "XRAY_BASE64"
    assert headers_of(data) == {"routing": LINKS["happ_routing"]}
    assert any("created" in s for s in summary)


def test_apply_changes_creates_incy_rule_when_missing():
    data = settings()
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    created = data["responseRules"]["rules"][0]
    assert created["name"] == "Incy"
    assert headers_of(data) == {
        "routing": LINKS["incy_routing"],
        "autorouting": LINKS["incy_autorouting"],
    }


def test_apply_changes_updates_both_clients_in_place():
    # The realistic case: both rules already exist, each with unrelated headers.
    data = settings(
        responseRules={
            "version": "1",
            "rules": [
                {
                    "name": "Happ",
                    "enabled": True,
                    "responseType": "XRAY_JSON",
                    "responseModifications": {
                        "headers": [{"key": "routing", "value": "happ://old"}]
                    },
                },
                {
                    "name": "Incy",
                    "enabled": True,
                    "responseType": "XRAY_JSON",
                    "responseModifications": {
                        "headers": [
                            {"key": "autorouting", "value": "incy://old-auto"},
                            {"key": "routing", "value": "incy://old"},
                            {"key": "support-email", "value": " "},
                        ]
                    },
                },
            ],
        }
    )
    core.apply_changes(data, LINKS, enable_happ=True, enable_incy=True)

    assert headers_of(data, 0) == {"routing": LINKS["happ_routing"]}
    assert headers_of(data, 1) == {
        "autorouting": LINKS["incy_autorouting"],
        "routing": LINKS["incy_routing"],
        "support-email": " ",  # untouched
    }
    # No extra rules were invented
    assert len(data["responseRules"]["rules"]) == 2


def test_apply_changes_keeps_existing_response_type():
    data = settings(
        responseRules={"version": "1", "rules": [{"name": "Incy", "responseType": "XRAY_JSON"}]}
    )
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    assert data["responseRules"]["rules"][0]["responseType"] == "XRAY_JSON"


def test_apply_changes_respects_custom_rule_name_match():
    data = settings(responseRules={"version": "1", "rules": [{"name": "Happ clients (mobile)"}]})
    core.apply_changes(data, LINKS, enable_happ=True, enable_incy=False, happ_match="happ clients")
    assert headers_of(data) == {"routing": LINKS["happ_routing"]}
    assert len(data["responseRules"]["rules"]) == 1


def test_apply_changes_does_not_create_when_creation_is_off():
    data = settings()
    summary = core.apply_changes(
        data, LINKS, enable_happ=True, enable_incy=False, create_missing=False
    )
    assert data["responseRules"] is None  # completely untouched
    assert any("skipped" in s for s in summary)


def test_apply_changes_skips_autorouting_on_created_rule_when_disabled():
    data = settings()
    core.apply_changes(data, LINKS, enable_happ=False, enable_incy=True, incy_autorouting=False)
    assert set(headers_of(data)) == {"routing"}


def test_apply_changes_strips_stale_autorouting_from_existing_rule():
    # A rule that already carries an autorouting header must lose it once autorouting
    # is disabled — otherwise clients keep hitting the old link.
    data = settings(
        responseRules={
            "version": "1",
            "rules": [
                {
                    "name": "Incy",
                    "responseType": "XRAY_JSON",
                    "responseModifications": {
                        "headers": [{"key": "autorouting", "value": "incy://old"}]
                    },
                }
            ],
        }
    )
    core.apply_changes(data, LINKS, enable_happ=False, enable_incy=True, incy_autorouting=False)
    assert set(headers_of(data)) == {"routing"}


def test_apply_changes_does_nothing_when_both_disabled():
    data = {"foo": "bar"}
    summary = core.apply_changes(data, LINKS, enable_happ=False, enable_incy=False)
    assert summary == []
    assert data == {"foo": "bar"}


# --------------------------------------------------------------------------- #
# version handling
# --------------------------------------------------------------------------- #


def test_detect_major_version_from_payload_shape():
    assert remnawave.detect_major_version({"uuid": UUID, "happRouting": None}) == 2
    assert remnawave.detect_major_version({"uuid": UUID, "profileTitle": "x"}) == 2
    assert remnawave.detect_major_version({"uuid": UUID, "customResponseHeaders": {}}) == 3
    assert remnawave.detect_major_version(None) is None


def test_resolve_major_version_prefers_explicit_config():
    v2_payload = {"happRouting": None}
    assert core.resolve_major_version(v2_payload, configured="3") == 3
    assert core.resolve_major_version(v2_payload, configured="auto") == 2
    assert core.resolve_major_version(v2_payload, configured="nonsense") == 2  # falls back


def test_legacy_cleanup_is_noop_on_v3():
    data = {"uuid": UUID}
    assert core.legacy_happ_cleanup(data, 3, enabled=True) == {}


def test_legacy_cleanup_warns_but_keeps_value_when_disabled():
    data = {"uuid": UUID, "happRouting": "happ://old"}
    assert core.legacy_happ_cleanup(data, 2, enabled=False) == {}
    assert data["happRouting"] == "happ://old"


def test_legacy_cleanup_nulls_field_when_enabled():
    data = {"uuid": UUID, "happRouting": "happ://old"}
    assert core.legacy_happ_cleanup(data, 2, enabled=True) == {"happRouting": None}
    assert data["happRouting"] is None


# --------------------------------------------------------------------------- #
# PATCH payload
# --------------------------------------------------------------------------- #


def test_patch_payload_sends_only_what_we_changed():
    data = {
        "uuid": UUID,
        "responseRules": {"version": "1", "rules": []},
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2026-01-02T00:00:00.000Z",
        "customResponseHeaders": {"announce": "base64:..."},
        "hwidSettings": {"hwidDeviceLimit": 3},
    }
    payload = remnawave.build_patch_payload(data)
    # Read-only fields and settings we do not manage must not be echoed back.
    assert payload == {"uuid": UUID, "responseRules": {"version": "1", "rules": []}}


def test_patch_payload_merges_extra_fields():
    data = {"uuid": UUID, "responseRules": {"version": "1", "rules": []}}
    payload = remnawave.build_patch_payload(data, {"happRouting": None})
    assert payload["happRouting"] is None


def test_patch_payload_rejects_payload_without_uuid():
    try:
        remnawave.build_patch_payload({"responseRules": {}})
    except ValueError as e:
        assert "uuid" in str(e)
    else:
        raise AssertionError("expected ValueError")


# --------------------------------------------------------------------------- #
# geo + full cycle
# --------------------------------------------------------------------------- #


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
        core.geobuild,
        "trim_all",
        lambda cache, out, site, ip: seen.update(cache=cache, out=out, site=site, ip=ip) or True,
    )
    monkeypatch.setattr(
        core.checksums, "write_sidecars", lambda directory: seen.setdefault("cksum_dir", directory)
    )

    template = {"DirectSites": ["geosite:private"], "DirectIp": ["geoip:private"]}
    assert core.refresh_geo(template) is True
    assert seen["mirror_dir"] == core.GEO_CACHE_DIR  # full downloaded into the private cache
    assert seen["cache"] == core.GEO_CACHE_DIR
    assert seen["out"] == core.GEO_DIR  # trimmed into the served dir
    assert seen["site"] == {"PRIVATE"}
    assert seen["ip"] == {"PRIVATE"}
    assert seen["cksum_dir"] == core.GEO_DIR  # checksum sidecars for the served files


def stub_io(monkeypatch):
    """Cut every filesystem/network dependency out of one update cycle.

    ``refresh_geo`` is stubbed too: without it the cycle would honour whatever
    GEO_MIRROR_ENABLED / OUTPUT_PATH happen to be in a developer's real .env and try
    to write to the container paths. Tests must not depend on the ambient environment.
    """
    monkeypatch.setattr(templating, "load_template", lambda: {"Name": "T"})
    monkeypatch.setattr(templating, "save_output", lambda template: True)
    monkeypatch.setattr(core, "refresh_geo", lambda template: True)
    monkeypatch.setattr(core, "STAMP_MODE", "interval")


def test_update_routing_pushes_minimal_patch(monkeypatch):
    stub_io(monkeypatch)
    monkeypatch.setattr(core, "ENABLE_HAPP", True)
    monkeypatch.setattr(core, "ENABLE_INCY", False)

    client = FakeClient(settings(customResponseHeaders={"announce": "base64:keepme"}))
    core.update_routing(client)

    assert client.patched is not None
    assert set(client.patched) == {"uuid", "responseRules"}  # nothing else is sent
    rule = client.patched["responseRules"]["rules"][0]
    header = rule["responseModifications"]["headers"][0]
    assert header["key"] == "routing"
    assert header["value"].startswith("happ://routing/onadd/")


def test_update_routing_bails_out_on_settings_without_uuid(monkeypatch):
    stub_io(monkeypatch)

    client = FakeClient({"responseRules": None})  # no uuid -> unusable
    core.update_routing(client)
    assert client.patched is None  # and no infinite retry loop


def test_created_rule_lands_above_the_catch_all_and_inherits_its_type():
    # On a stock panel the last rule is a conditionless "Fallback Base64". A rule
    # appended after it would be dead config, and a hardcoded responseType would
    # silently change what these clients receive.
    data = settings(
        responseRules={
            "version": "1",
            "rules": [
                {
                    "name": "Fallback Base64",
                    "enabled": True,
                    "operator": "AND",
                    "conditions": [],
                    "responseType": "XRAY_JSON",
                }
            ],
        }
    )
    summary = core.apply_changes(
        data,
        LINKS,
        enable_happ=True,
        enable_incy=True,
        happ_response_type="",
        incy_response_type="",
    )
    names = [r["name"] for r in data["responseRules"]["rules"]]
    assert names == ["Happ", "Incy", "Fallback Base64"]
    for rule in data["responseRules"]["rules"][:2]:
        assert rule["responseType"] == "XRAY_JSON"  # inherited, not hardcoded
    assert all("position" in s for s in summary)


def test_explicit_response_type_overrides_inheritance():
    data = settings(
        responseRules={
            "version": "1",
            "rules": [
                {"name": "Fallback", "enabled": True, "conditions": [], "responseType": "XRAY_JSON"}
            ],
        }
    )
    core.apply_changes(
        data, LINKS, enable_happ=True, enable_incy=False, happ_response_type="MIHOMO"
    )
    assert data["responseRules"]["rules"][0]["responseType"] == "MIHOMO"


def test_verify_autorouting_url_reports_mismatch(monkeypatch):
    monkeypatch.setattr(core.templating, "load_output", lambda: {"LastUpdated": "200"})

    class Resp:
        status_code = 200

        def json(self):
            return {"LastUpdated": "100"}  # proxy serving a stale copy

    monkeypatch.setattr(core.requests, "get", lambda url, timeout: Resp())
    assert core.verify_autorouting_url("https://sub.example/routing.json") is False


def test_verify_autorouting_url_accepts_matching_file(monkeypatch):
    monkeypatch.setattr(core.templating, "load_output", lambda: {"LastUpdated": "200"})

    class Resp:
        status_code = 200

        def json(self):
            return {"LastUpdated": "200"}

    monkeypatch.setattr(core.requests, "get", lambda url, timeout: Resp())
    assert core.verify_autorouting_url("https://sub.example/routing.json") is True


def test_verify_autorouting_url_never_raises_on_network_error(monkeypatch):
    monkeypatch.setattr(core.templating, "load_output", lambda: {"LastUpdated": "200"})

    def boom(url, timeout):
        raise core.requests.exceptions.ConnectionError("nope")

    monkeypatch.setattr(core.requests, "get", boom)
    assert core.verify_autorouting_url("https://sub.example/routing.json") is False
