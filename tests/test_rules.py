"""Unit tests for the pure rule logic. No network, no files — just data in, data out."""

from routing_updater import rules


def test_rule_matches_is_case_insensitive_and_fuzzy():
    assert rules.rule_matches({"name": "Incy"}, "incy")
    assert rules.rule_matches({"name": "my INCY vip"}, "incy")
    assert not rules.rule_matches({"name": "Happ"}, "incy")
    assert not rules.rule_matches({}, "incy")  # missing name must not crash


def test_upsert_header_updates_existing():
    headers = [{"key": "routing", "value": "old"}]
    rules.upsert_header(headers, "routing", "new")
    assert headers == [{"key": "routing", "value": "new"}]


def test_upsert_header_appends_when_missing():
    headers = [{"key": "routing", "value": "x"}]
    rules.upsert_header(headers, "autorouting", "y")
    assert {"key": "autorouting", "value": "y"} in headers
    assert len(headers) == 2


def test_apply_headers_preserves_existing_response_type():
    rule = {
        "name": "Incy",
        "responseType": "XRAY_JSON",
        "responseModifications": {"headers": [{"key": "routing", "value": "old"}]},
    }
    touched = rules.apply_headers_to_matching_rules(
        [rule], "incy", [("routing", "R"), ("autorouting", "A")]
    )
    assert touched == 1
    # responseType must stay exactly as the user set it
    assert rule["responseType"] == "XRAY_JSON"
    headers = rule["responseModifications"]["headers"]
    assert {"key": "routing", "value": "R"} in headers
    assert {"key": "autorouting", "value": "A"} in headers


def test_apply_headers_skips_non_matching_rules():
    rule = {"name": "SomethingElse"}
    touched = rules.apply_headers_to_matching_rules([rule], "incy", [("routing", "R")])
    assert touched == 0
    assert "responseModifications" not in rule


def test_build_incy_rule_uses_given_response_type():
    rule = rules.build_incy_rule("R", "A", "XRAY_BASE64")
    assert rule["name"] == "Incy"
    assert rule["responseType"] == "XRAY_BASE64"
    keys = {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing": "R", "autorouting": "A"}


def test_build_incy_rule_omits_autorouting_when_none():
    # No real AUTOROUTING_URL configured -> autorouting header must be absent, not blank.
    rule = rules.build_incy_rule("R", None, "XRAY_BASE64")
    keys = {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing": "R"}


def test_remove_header_drops_matching_key():
    headers = [{"key": "routing", "value": "R"}, {"key": "autorouting", "value": "A"}]
    assert rules.remove_header(headers, "autorouting") is True
    assert headers == [{"key": "routing", "value": "R"}]
    assert rules.remove_header(headers, "autorouting") is False  # nothing left to remove


def test_apply_headers_strips_stale_autorouting():
    rule = {
        "name": "Incy",
        "responseModifications": {
            "headers": [
                {"key": "routing", "value": "old"},
                {"key": "autorouting", "value": "stale"},
            ]
        },
    }
    rules.apply_headers_to_matching_rules(
        [rule], "incy", [("routing", "R")], remove_keys=("autorouting",)
    )
    keys = {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing": "R"}  # autorouting stripped, routing refreshed
