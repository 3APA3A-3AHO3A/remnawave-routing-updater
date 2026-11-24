"""v2run (iOS): its own routing-profile format, delivered through its own Response Rule.

The profile is converted from the same Happ-style template, so every client gets the
same rules, DNS and geo databases. The rule is handled like Happ / INCY: updated in
place, or created above the catch-all when missing.
"""

import base64
import copy
import json

from routing_updater import core, templating

UUID = "0f2b0b3e-0000-4000-8000-000000000000"

# The owner's real template, shortened.
TEMPLATE = {
    "Name": "FixErrorVPN",
    "GlobalProxy": "true",
    "RouteOrder": "block-proxy-direct",
    "RemoteDNSType": "DoH",
    "RemoteDNSDomain": "https://8.8.8.8/dns-query",
    "RemoteDNSIP": "8.8.8.8",
    "DomesticDNSType": "DoH",
    "DomesticDNSDomain": "https://77.88.8.8/dns-query",
    "DomesticDNSIP": "77.88.8.8",
    "Geoipurl": "https://sub.example/geoip.dat",
    "Geositeurl": "https://sub.example/geosite.dat",
    "DnsHosts": {},
    "DirectSites": ["geosite:private", "geosite:category-ru"],
    "DirectIp": ["geoip:private", "geoip:ru"],
    "ProxySites": ["geosite:youtube"],
    "ProxyIp": [],
    "BlockSites": [],
    "BlockIp": [],
    "DomainStrategy": "IPIfNonMatch",
    "FakeDNS": "false",
    "UseChunkFiles": "true",
    "LastUpdated": "1700000000",
}

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": None,
    "fixerrorvpn_routing": "fixerrorvpn://routing/onadd/B64",
    "fixerrorvpn_autorouting": None,
    "v2run_routing": "v2run://routing/onadd/V2RUN",
}


def decode(link):
    payload = link.removeprefix("v2run://routing/onadd/")
    return json.loads(base64.b64decode(payload))


def rule(name, ua, headers=(), response_type="XRAY_JSON"):
    return {
        "name": name,
        "enabled": True,
        "operator": "AND",
        "conditions": [{"headerName": "user-agent", "operator": "CONTAINS", "value": ua}],
        "responseType": response_type,
        "responseModifications": {"headers": [{"key": k, "value": v} for k, v in headers]},
    }


def panel(*rules):
    return {"uuid": UUID, "responseRules": {"version": "1", "rules": list(rules)}}


def fallback():
    return {"name": "Fallback Base64", "enabled": True, "responseType": "XRAY_BASE64"}


def headers(r):
    return [(h["key"], h["value"]) for h in r["responseModifications"]["headers"]]


def run(data, **kwargs):
    kwargs.setdefault("enable_happ", False)
    kwargs.setdefault("enable_incy", False)
    kwargs.setdefault("enable_v2run", True)
    return core.apply_changes(data, LINKS, **kwargs)


# --------------------------------------------------------------------------- #
# template -> v2run profile
# --------------------------------------------------------------------------- #


def test_profile_carries_the_same_rules_dns_and_geo():
    assert templating.to_v2run_profile(copy.deepcopy(TEMPLATE)) == {
        "v2run": 1,
        "profile": {
            "name": "FixErrorVPN",
            "globalProxy": True,
            "routeOrder": ["BLOCK", "PROXY", "DIRECT"],
            "domainStrategy": "IPIfNonMatch",
            "direct": {
                "sites": ["geosite:private", "geosite:category-ru"],
                "ips": ["geoip:private", "geoip:ru"],
            },
            "proxy": {"sites": ["geosite:youtube"]},
            "dns": {
                "remote": {"type": "DOH", "address": "https://8.8.8.8/dns-query"},
                "domestic": {
                    "type": "DOH",
                    "address": "https://77.88.8.8/dns-query",
                    "direct": True,
                },
                "fakeDns": False,
            },
            "geo": {
                "geositeUrl": "https://sub.example/geosite.dat?v=1700000000",
                "geoipUrl": "https://sub.example/geoip.dat?v=1700000000",
            },
        },
    }


def test_geo_urls_change_with_the_stamp():
    first = templating.to_v2run_profile(dict(TEMPLATE, LastUpdated="1"))
    second = templating.to_v2run_profile(dict(TEMPLATE, LastUpdated="2"))
    assert first["profile"]["geo"] != second["profile"]["geo"]
    assert first["profile"]["dns"] == second["profile"]["dns"]


def test_geo_url_with_query_gets_an_extra_parameter():
    profile = templating.to_v2run_profile(dict(TEMPLATE, Geoipurl="https://d/geoip.dat?x=1"))
    assert profile["profile"]["geo"]["geoipUrl"] == "https://d/geoip.dat?x=1&v=1700000000"


def test_unstamped_template_keeps_plain_geo_urls():
    template = dict(TEMPLATE)
    del template["LastUpdated"]
    geo = templating.to_v2run_profile(template)["profile"]["geo"]
    assert geo == {
        "geositeUrl": "https://sub.example/geosite.dat",
        "geoipUrl": "https://sub.example/geoip.dat",
    }


def test_dou_uses_the_ip_and_hosts_and_block_lists_are_kept():
    template = dict(
        TEMPLATE,
        DomesticDNSType="DoU",
        DnsHosts={"dns.google": "8.8.8.8"},
        BlockSites=["geosite:category-ads-all"],
        BlockIp=["1.2.3.4/32"],
        FakeDNS="true",
    )
    profile = templating.to_v2run_profile(template)["profile"]
    assert profile["dns"]["domestic"] == {"type": "DOU", "address": "77.88.8.8", "direct": True}
    assert profile["dns"]["hosts"] == {"dns.google": "8.8.8.8"}
    assert profile["dns"]["fakeDns"] is True
    assert profile["block"] == {"sites": ["geosite:category-ads-all"], "ips": ["1.2.3.4/32"]}


def test_minimal_template_yields_a_minimal_profile():
    profile = templating.to_v2run_profile({"GlobalProxy": "false", "RouteOrder": "nonsense"})
    # Only the name is required by v2run; unusable or absent fields are left out.
    assert profile == {"v2run": 1, "profile": {"name": "Routing", "globalProxy": False}}


def test_build_links_has_a_v2run_link_with_its_own_payload():
    links = templating.build_links(copy.deepcopy(TEMPLATE))
    happ_payload = links["happ_routing"].removeprefix("happ://routing/onadd/")
    assert links["v2run_routing"].startswith("v2run://routing/onadd/")
    assert not links["v2run_routing"].endswith(happ_payload)
    assert decode(links["v2run_routing"]) == templating.to_v2run_profile(TEMPLATE)


# --------------------------------------------------------------------------- #
# Response Rules
# --------------------------------------------------------------------------- #


def test_updates_the_v2run_rule_and_leaves_v2raytun_alone():
    data = panel(
        rule("v2run", "v2run", [("announce-url", "https://help"), ("routing", "OLD")]),
        rule("v2raytun", "v2raytun", [("announce-url", "https://help")]),
        fallback(),
    )
    before = copy.deepcopy(data)

    summary = run(data)

    v2run, v2raytun, catch_all = data["responseRules"]["rules"]
    assert headers(v2run) == [
        ("announce-url", "https://help"),
        ("routing", LINKS["v2run_routing"]),
    ]
    assert v2raytun == before["responseRules"]["rules"][1]
    assert catch_all == before["responseRules"]["rules"][2]
    assert summary == ["v2run: 1 rule(s) updated"]


def test_creates_a_rule_above_the_catch_all_when_missing():
    data = panel(rule("Happ", "Happ"), fallback())

    summary = run(data)

    rules = data["responseRules"]["rules"]
    assert [r["name"] for r in rules] == ["Happ", "v2run", "Fallback Base64"]
    created = rules[1]
    assert created["conditions"][0]["value"] == "v2run"
    assert created["responseType"] == "XRAY_BASE64"  # inherited from the catch-all
    assert headers(created) == [("routing", LINKS["v2run_routing"])]
    assert summary == ["v2run: no rule found — created at position 2 (responseType XRAY_BASE64)"]


def test_explicit_response_type_for_a_created_rule():
    data = panel(fallback())
    run(data, v2run_response_type="XRAY_JSON")
    assert data["responseRules"]["rules"][0]["responseType"] == "XRAY_JSON"


def test_creation_off_only_warns():
    data = panel(fallback())
    before = copy.deepcopy(data)
    assert run(data, create_missing=False) == ["v2run: no rule found — skipped"]
    assert data == before


def test_disabled_toggle_does_nothing():
    data = panel(rule("v2run", "v2run"), fallback())
    before = copy.deepcopy(data)
    assert run(data, enable_v2run=False) == []
    assert data == before


def test_happ_rule_does_not_get_the_v2run_link():
    data = panel(rule("Happ", "Happ"), rule("v2run", "v2run"), fallback())

    run(data, enable_happ=True)

    happ, v2run = data["responseRules"]["rules"][:2]
    assert headers(happ) == [("routing", LINKS["happ_routing"])]
    assert headers(v2run) == [("routing", LINKS["v2run_routing"])]


def test_update_routing_sends_the_v2run_profile(monkeypatch):
    monkeypatch.setattr(templating, "load_template", lambda: copy.deepcopy(TEMPLATE))
    monkeypatch.setattr(templating, "save_output", lambda template: True)
    monkeypatch.setattr(core, "refresh_geo", lambda template: True)
    monkeypatch.setattr(core, "STAMP_MODE", "interval")
    monkeypatch.setattr(core, "GEOIP_URL", "https://mirror.example/geoip.dat")
    monkeypatch.setattr(core, "GEOSITE_URL", "https://mirror.example/geosite.dat")
    monkeypatch.setattr(core, "ENABLE_HAPP", False)
    monkeypatch.setattr(core, "ENABLE_INCY", False)
    monkeypatch.setattr(core, "ENABLE_FIXERRORVPN", False)
    monkeypatch.setattr(core, "ENABLE_V2RUN", True)

    class Client:
        patched = None

        def get_settings(self):
            return panel(rule("v2run", "v2run", [("routing", "OLD")]), fallback())

        def patch_settings(self, data):
            self.patched = data

    client = Client()
    core.update_routing(client)

    v2run = client.patched["responseRules"]["rules"][0]
    profile = decode(dict(headers(v2run))["routing"])["profile"]
    # The mirror URLs from .env reach v2run too, versioned with the fresh stamp.
    assert profile["geo"]["geoipUrl"].startswith("https://mirror.example/geoip.dat?v=")
    assert profile["geo"]["geositeUrl"].startswith("https://mirror.example/geosite.dat?v=")
    assert profile["name"] == "FixErrorVPN"


def test_same_stamp_means_same_link_so_on_geo_change_stays_quiet():
    # STAMP_MODE=on_geo_change compares the rules before and after: with the stamp kept,
    # the v2run link must come out byte-for-byte identical, or every cycle would PATCH.
    first = templating.build_links(dict(TEMPLATE))["v2run_routing"]
    second = templating.build_links(dict(TEMPLATE))["v2run_routing"]
    assert first == second

    data = panel(rule("v2run", "v2run", [("routing", first)]), fallback())
    before = copy.deepcopy(data)
    core.apply_changes(
        data,
        dict(LINKS, v2run_routing=second),
        enable_happ=False,
        enable_incy=False,
        enable_v2run=True,
    )
    assert data == before
