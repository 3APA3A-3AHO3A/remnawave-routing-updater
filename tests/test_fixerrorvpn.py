"""FixErrorVPN (Windows app): routing / autorouting headers in its own Response Rules.

Unlike Happ and INCY, FixErrorVPN rules are never created by the updater — they match
the app's User-Agent and are set up by the panel owner. These tests pin that down,
together with the "touch only our two headers" contract.
"""

import copy
import logging

from routing_updater import core, templating

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": "incy://autorouting/onadd/https://sub.example/routing.json",
    "fixerrorvpn_routing": "fixerrorvpn://routing/onadd/B64",
    "fixerrorvpn_autorouting": "fixerrorvpn://autorouting/onadd/https://sub.example/routing.json",
}

UUID = "0f2b0b3e-0000-4000-8000-000000000000"
UA_CONDITION = {
    "headerName": "user-agent",
    "operator": "CONTAINS",
    "value": "FixErrorVPN",
    "caseSensitive": False,
}


def fixerror_rule(name, response_type, headers, enabled=True):
    return {
        "name": name,
        "enabled": enabled,
        "operator": "AND",
        "conditions": [dict(UA_CONDITION)],
        "responseType": response_type,
        "responseModifications": {"headers": headers},
    }


def panel_with_fixerror_rules():
    """The owner's real layout: two FixErrorVPN rules above the generic ones."""
    return {
        "uuid": UUID,
        "responseRules": {
            "version": "1",
            "rules": [
                fixerror_rule(
                    "FixErrorVPN Xray",
                    "XRAY_JSON",
                    [
                        {"key": "fixerror-logo", "value": "https://example.org/logo.svg"},
                        {"key": "routing", "value": "fixerrorvpn://routing/onadd/OLD"},
                        {"key": "fixerror-color", "value": "#1f6feb"},
                    ],
                ),
                fixerror_rule(
                    "FixErrorVPN Mihomo",
                    "MIHOMO",
                    [{"key": "fixerror-buttons", "value": "[]"}],
                    enabled=False,
                ),
                {
                    "name": "Xray",
                    "enabled": True,
                    "conditions": [
                        {"headerName": "user-agent", "operator": "CONTAINS", "value": "Xray"}
                    ],
                    "responseType": "XRAY_JSON",
                    "responseModifications": {"headers": [{"key": "x-keep", "value": "1"}]},
                },
                {"name": "Fallback Base64", "enabled": True, "responseType": "XRAY_BASE64"},
            ],
        },
    }


def rules_of(data):
    return data["responseRules"]["rules"]


def headers(rule):
    return [(h["key"], h["value"]) for h in rule["responseModifications"]["headers"]]


def run(data, **kwargs):
    kwargs.setdefault("enable_happ", False)
    kwargs.setdefault("enable_incy", False)
    kwargs.setdefault("enable_fixerrorvpn", True)
    return core.apply_changes(data, LINKS, **kwargs)


def test_build_links_uses_the_same_payload_as_happ():
    links = templating.build_links({"Name": "T", "LastUpdated": "1"})
    payload = links["happ_routing"].removeprefix("happ://routing/onadd/")
    assert links["fixerrorvpn_routing"] == f"fixerrorvpn://routing/onadd/{payload}"
    assert links["incy_routing"].endswith(payload)


def test_updates_every_matching_rule_and_leaves_foreign_headers_alone():
    data = panel_with_fixerror_rules()
    before = copy.deepcopy(data)

    summary = run(data)

    xray, mihomo, generic, fallback = rules_of(data)
    # routing is rewritten in place, autorouting appended; the owner's headers keep
    # their values and their order.
    assert headers(xray) == [
        ("fixerror-logo", "https://example.org/logo.svg"),
        ("routing", LINKS["fixerrorvpn_routing"]),
        ("fixerror-color", "#1f6feb"),
        ("autorouting", LINKS["fixerrorvpn_autorouting"]),
    ]
    assert headers(mihomo) == [
        ("fixerror-buttons", "[]"),
        ("routing", LINKS["fixerrorvpn_routing"]),
        ("autorouting", LINKS["fixerrorvpn_autorouting"]),
    ]
    # Everything except our two headers is exactly as the panel had it.
    for new, old in zip(rules_of(data), rules_of(before), strict=True):
        for field in ("name", "enabled", "conditions", "responseType", "operator"):
            assert new.get(field) == old.get(field)
    assert generic == rules_of(before)[2]
    assert fallback == rules_of(before)[3]
    assert summary == ["FixErrorVPN: 2 rule(s) updated"]


def test_never_creates_a_rule_and_warns(caplog):
    data = {"uuid": UUID, "responseRules": None}
    with caplog.at_level(logging.WARNING, logger="RoutingUpdater"):
        summary = run(data, create_missing=True)  # creation on for others, not for us

    assert data == {"uuid": UUID, "responseRules": None}
    assert summary == ["FixErrorVPN: no rule found — skipped"]
    assert any("FixErrorVPN" in r.getMessage() for r in caplog.records)


def test_no_matching_rule_leaves_existing_rules_untouched():
    data = panel_with_fixerror_rules()
    del rules_of(data)[0:2]  # only the generic rules are left
    before = copy.deepcopy(data)

    summary = run(data)

    assert data == before
    assert summary == ["FixErrorVPN: no rule found — skipped"]


def test_without_autorouting_url_routing_only_and_stale_autorouting_removed():
    data = panel_with_fixerror_rules()
    rules_of(data)[0]["responseModifications"]["headers"].append(
        {"key": "autorouting", "value": "fixerrorvpn://autorouting/onadd/https://old"}
    )

    summary = run(data, fixerrorvpn_autorouting=False)

    xray, mihomo = rules_of(data)[:2]
    assert headers(xray) == [
        ("fixerror-logo", "https://example.org/logo.svg"),
        ("routing", LINKS["fixerrorvpn_routing"]),
        ("fixerror-color", "#1f6feb"),
    ]
    assert headers(mihomo) == [
        ("fixerror-buttons", "[]"),
        ("routing", LINKS["fixerrorvpn_routing"]),
    ]
    assert summary == ["FixErrorVPN: 2 rule(s) updated (routing only, autorouting skipped)"]


def test_null_autorouting_link_counts_as_not_configured():
    data = panel_with_fixerror_rules()
    links = dict(LINKS, fixerrorvpn_autorouting=None)
    core.apply_changes(data, links, enable_happ=False, enable_incy=False, enable_fixerrorvpn=True)
    assert "autorouting" not in dict(headers(rules_of(data)[0]))


def test_clients_do_not_pick_up_each_others_rules():
    data = panel_with_fixerror_rules()
    rules_of(data).insert(
        2, {"name": "Happ", "responseType": "XRAY_JSON", "responseModifications": {"headers": []}}
    )

    run(data, enable_happ=True)

    xray, _, happ = rules_of(data)[:3]
    assert dict(headers(xray))["routing"] == LINKS["fixerrorvpn_routing"]
    assert headers(happ) == [("routing", LINKS["happ_routing"])]
    assert len(rules_of(data)) == 5  # nothing created, nothing removed


def test_custom_rule_name_match():
    data = panel_with_fixerror_rules()
    rules_of(data)[0]["name"] = "Windows app (Xray)"

    summary = run(data, fixerrorvpn_match="windows app")

    assert dict(headers(rules_of(data)[0]))["routing"] == LINKS["fixerrorvpn_routing"]
    assert "routing" not in dict(headers(rules_of(data)[1]))  # no longer matches
    assert summary == ["FixErrorVPN: 1 rule(s) updated"]


def test_disabled_toggle_does_nothing():
    data = panel_with_fixerror_rules()
    before = copy.deepcopy(data)
    assert run(data, enable_fixerrorvpn=False) == []
    assert data == before


def test_update_routing_sends_fixerrorvpn_headers(monkeypatch):
    monkeypatch.setattr(templating, "load_template", lambda: {"Name": "T"})
    monkeypatch.setattr(templating, "save_output", lambda template: True)
    monkeypatch.setattr(core, "refresh_geo", lambda template: True)
    monkeypatch.setattr(core, "STAMP_MODE", "interval")
    monkeypatch.setattr(core, "ENABLE_HAPP", False)
    monkeypatch.setattr(core, "ENABLE_INCY", False)
    monkeypatch.setattr(core, "ENABLE_FIXERRORVPN", True)

    class Client:
        patched = None

        def get_settings(self):
            return panel_with_fixerror_rules()

        def patch_settings(self, data):
            self.patched = data

    client = Client()
    core.update_routing(client)

    xray = client.patched["responseRules"]["rules"][0]
    routing = dict(headers(xray))["routing"]
    assert routing.startswith("fixerrorvpn://routing/onadd/")
    assert routing != "fixerrorvpn://routing/onadd/OLD"
