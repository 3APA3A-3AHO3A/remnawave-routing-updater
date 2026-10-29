"""Panel re-sync in STAMP_MODE=on_geo_change and extra Happ rules picked by full name.

With an unchanged geo database the stamp (LastUpdated) stays put, but the panel is still
compared against what it should carry: a newly enabled client or a header removed by hand
is fixed on the next cycle, without telling clients to re-download anything.
"""

import base64
import copy
import json

from routing_updater import core, state, templating

UUID = "0f2b0b3e-0000-4000-8000-000000000000"
STAMP = "1700000000"

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": None,
    "fixerrorvpn_routing": "fixerrorvpn://routing/onadd/B64",
    "fixerrorvpn_autorouting": None,
}


def rule(name, headers=()):
    return {
        "name": name,
        "enabled": True,
        "conditions": [{"headerName": "user-agent", "operator": "CONTAINS", "value": name}],
        "responseType": "XRAY_JSON",
        "responseModifications": {"headers": [{"key": k, "value": v} for k, v in headers]},
    }


def panel(*rules):
    return {"uuid": UUID, "responseRules": {"version": "1", "rules": list(rules)}}


def headers(data, name):
    for r in data["responseRules"]["rules"]:
        if r["name"] == name:
            return {h["key"]: h["value"] for h in r["responseModifications"]["headers"]}
    raise AssertionError(f"no rule {name}")


class Client:
    def __init__(self, settings):
        self.settings = settings
        self.patched = None

    def get_settings(self):
        return copy.deepcopy(self.settings)

    def patch_settings(self, data):
        self.patched = data


def on_change_cycle(monkeypatch, saved):
    """One update cycle in on_geo_change mode with an unchanged database."""
    monkeypatch.setattr(templating, "load_template", lambda: {"Name": "T"})
    monkeypatch.setattr(templating, "save_output", lambda template: True)
    monkeypatch.setattr(core, "refresh_geo", lambda template: False)  # 304, nothing new
    monkeypatch.setattr(core, "STAMP_MODE", "on_geo_change")
    monkeypatch.setattr(state, "load_state", lambda: {"last_updated": STAMP, "applied": True})
    monkeypatch.setattr(state, "save_state", lambda data: saved.update(data))
    monkeypatch.setattr(core, "ENABLE_HAPP", True)
    monkeypatch.setattr(core, "ENABLE_INCY", False)
    monkeypatch.setattr(core, "ENABLE_FIXERRORVPN", True)
    monkeypatch.setattr(core, "AUTOROUTING_ENABLED", False)


def expected_links():
    template = templating.stamp_template({"Name": "T"}, STAMP)
    return templating.build_links(template)


# --------------------------------------------------------------------------- #
# re-sync with an unchanged database
# --------------------------------------------------------------------------- #


def test_unchanged_db_still_fills_a_newly_enabled_client(monkeypatch):
    saved = {}
    on_change_cycle(monkeypatch, saved)
    links = expected_links()
    # Happ is already up to date; the FixErrorVPN rule has never been written.
    client = Client(
        panel(
            rule("FixErrorVPN Xray", [("fixerror-logo", "L")]),
            rule("Happ", [("routing", links["happ_routing"])]),
        )
    )

    core.update_routing(client)

    assert client.patched is not None
    fixerror = headers(client.patched, "FixErrorVPN Xray")
    assert fixerror == {"fixerror-logo": "L", "routing": links["fixerrorvpn_routing"]}
    # The stamp did not move: LastUpdated is still the one from the saved state.
    payload = fixerror["routing"].split("onadd/", 1)[1]
    assert json.loads(base64.b64decode(payload))["LastUpdated"] == STAMP
    assert saved["applied"] is True


def test_unchanged_db_and_panel_up_to_date_sends_nothing(monkeypatch):
    saved = {}
    on_change_cycle(monkeypatch, saved)
    links = expected_links()
    client = Client(
        panel(
            rule(
                "FixErrorVPN Xray",
                [("fixerror-logo", "L"), ("routing", links["fixerrorvpn_routing"])],
            ),
            rule("Happ", [("routing", links["happ_routing"])]),
        )
    )

    core.update_routing(client)

    assert client.patched is None
    assert saved["applied"] is True


def test_unchanged_db_restores_a_header_removed_by_hand(monkeypatch):
    saved = {}
    on_change_cycle(monkeypatch, saved)
    links = expected_links()
    client = Client(
        panel(
            rule("FixErrorVPN Xray", [("routing", links["fixerrorvpn_routing"])]),
            rule("Happ", [("support-url", "S")]),  # routing deleted in the panel
        )
    )

    core.update_routing(client)

    assert headers(client.patched, "Happ") == {"support-url": "S", "routing": links["happ_routing"]}
    assert set(client.patched) == {"uuid", "responseRules"}


# --------------------------------------------------------------------------- #
# HAPP_EXTRA_RULES
# --------------------------------------------------------------------------- #


def run(data, **kwargs):
    kwargs.setdefault("enable_happ", True)
    kwargs.setdefault("enable_incy", False)
    kwargs.setdefault("enable_fixerrorvpn", True)
    kwargs.setdefault("happ_extra_rules", ("xray",))
    return core.apply_changes(data, LINKS, **kwargs)


def test_extra_rule_gets_the_happ_routing_header_by_full_name():
    data = panel(
        rule("FixErrorVPN Xray", [("fixerror-logo", "L")]),
        rule("Xray", [("routing", "happ://routing/onadd/OLD")]),
        rule("Happ"),
    )

    summary = run(data)

    assert headers(data, "Xray") == {"routing": LINKS["happ_routing"]}
    assert headers(data, "Happ") == {"routing": LINKS["happ_routing"]}
    # "xray" is a full-name match: the FixErrorVPN rule keeps its own scheme.
    assert headers(data, "FixErrorVPN Xray") == {
        "fixerror-logo": "L",
        "routing": LINKS["fixerrorvpn_routing"],
    }
    assert summary[0] == "Happ: 1 rule(s) updated + Xray"


def test_extra_rule_alone_does_not_stop_the_happ_rule_from_being_created():
    data = panel(rule("Xray"), {"name": "Fallback Base64", "responseType": "XRAY_BASE64"})

    summary = run(data, enable_fixerrorvpn=False)

    names = [r["name"] for r in data["responseRules"]["rules"]]
    assert names == ["Xray", "Happ", "Fallback Base64"]
    assert headers(data, "Xray") == {"routing": LINKS["happ_routing"]}
    assert summary[0].startswith("Happ: no rule found — created at position 2")


def test_extra_rule_is_never_created_and_missing_one_only_warns(caplog):
    data = panel(rule("Happ"))
    before_names = [r["name"] for r in data["responseRules"]["rules"]]

    summary = run(data, enable_fixerrorvpn=False)

    assert [r["name"] for r in data["responseRules"]["rules"]] == before_names
    assert summary == ["Happ: 1 rule(s) updated"]
    assert any("HAPP_EXTRA_RULES" in r.getMessage() for r in caplog.records)


def test_extra_rule_that_is_also_the_happ_rule_is_counted_once():
    data = panel(rule("Happ"))
    summary = run(data, enable_fixerrorvpn=False, happ_extra_rules=("happ",))
    assert summary[0].startswith("Happ: 1 rule(s) updated")
    assert "+" not in summary[0]
