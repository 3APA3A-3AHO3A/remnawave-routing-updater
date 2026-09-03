"""Unit tests for the pure rule logic. No network, no files — just data in, data out."""

from routing_updater import rules


def test_rule_matches_is_case_insensitive_and_fuzzy():
    assert rules.rule_matches({"name": "Incy"}, "incy")
    assert rules.rule_matches({"name": "my INCY vip"}, "incy")
    assert not rules.rule_matches({"name": "Happ"}, "incy")
    assert not rules.rule_matches({}, "incy")  # missing name must not crash
    assert not rules.rule_matches(None, "incy")  # junk entry in the rules array


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


def test_apply_headers_never_touches_unrelated_headers():
    # The panel usually carries extra headers on the same rule (support-email,
    # announce-url, ...). They must survive untouched and keep their position.
    rule = {
        "name": "Incy",
        "responseType": "XRAY_JSON",
        "responseModifications": {
            "headers": [
                {"key": "autorouting", "value": "old-auto"},
                {"key": "routing", "value": "old-routing"},
                {"key": "support-email", "value": " "},
                {"key": "profile-web-page-url", "value": " "},
                {"key": "announce-url", "value": " "},
            ]
        },
    }
    rules.apply_headers_to_matching_rules([rule], "incy", [("routing", "R"), ("autorouting", "A")])
    assert rule["responseModifications"]["headers"] == [
        {"key": "autorouting", "value": "A"},
        {"key": "routing", "value": "R"},
        {"key": "support-email", "value": " "},
        {"key": "profile-web-page-url", "value": " "},
        {"key": "announce-url", "value": " "},
    ]


def test_apply_headers_keeps_conditions_and_enabled_flag():
    rule = {
        "name": "Happ",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "CONTAINS",
                "value": "Happ",
                "caseSensitive": False,
            }
        ],
        "responseType": "XRAY_JSON",
        "responseModifications": {"headers": [{"key": "routing", "value": "old"}]},
    }
    before_conditions = [dict(c) for c in rule["conditions"]]
    rules.apply_headers_to_matching_rules([rule], "happ", [("routing", "R")])
    assert rule["conditions"] == before_conditions
    assert rule["enabled"] is True
    assert rule["operator"] == "AND"


def test_apply_headers_handles_rule_without_modifications():
    rule = {"name": "Happ", "responseType": "XRAY_JSON"}
    assert rules.apply_headers_to_matching_rules([rule], "happ", [("routing", "R")]) == 1
    assert rule["responseModifications"]["headers"] == [{"key": "routing", "value": "R"}]


def test_apply_headers_handles_null_headers_array():
    # The panel may serialise an empty modifications block with headers: null.
    rule = {"name": "Happ", "responseModifications": {"headers": None}}
    rules.apply_headers_to_matching_rules([rule], "happ", [("routing", "R")])
    assert rule["responseModifications"]["headers"] == [{"key": "routing", "value": "R"}]


def test_apply_headers_skips_non_matching_rules():
    rule = {"name": "SomethingElse"}
    touched = rules.apply_headers_to_matching_rules([rule], "incy", [("routing", "R")])
    assert touched == 0
    assert "responseModifications" not in rule


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


def test_build_client_rule_shape():
    rule = rules.build_client_rule(
        "Incy", "Incy", [("routing", "R"), ("autorouting", "A")], "XRAY_BASE64"
    )
    assert rule["name"] == "Incy"
    assert rule["enabled"] is True
    assert rule["responseType"] == "XRAY_BASE64"
    assert rule["conditions"] == [
        {
            "headerName": "user-agent",
            "operator": "CONTAINS",
            "value": "Incy",
            "caseSensitive": False,
        }
    ]
    keys = {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing": "R", "autorouting": "A"}


def test_build_client_rule_omits_falsy_headers():
    # No real AUTOROUTING_URL configured -> autorouting header must be absent, not blank.
    rule = rules.build_client_rule(
        "Incy", "Incy", [("routing", "R"), ("autorouting", None)], "XRAY_BASE64"
    )
    keys = {h["key"]: h["value"] for h in rule["responseModifications"]["headers"]}
    assert keys == {"routing": "R"}


def test_ensure_rules_config_creates_container_from_scratch():
    data = {}
    rule_list = rules.ensure_rules_config(data)
    rule_list.append({"name": "Happ"})
    assert data["responseRules"]["version"] == rules.RESPONSE_RULES_VERSION
    assert data["responseRules"]["rules"] == [{"name": "Happ"}]


def test_ensure_rules_config_replaces_null_container():
    # A panel that has never had a rule returns responseRules: null — setdefault would
    # keep the None and blow up on the next access.
    data = {"responseRules": None}
    rule_list = rules.ensure_rules_config(data)
    assert rule_list == []
    assert data["responseRules"]["version"] == rules.RESPONSE_RULES_VERSION


def test_ensure_rules_config_preserves_existing_settings():
    data = {
        "responseRules": {
            "version": "1",
            "settings": {"disableSubscriptionAccessByPath": True},
            "rules": [{"name": "Happ"}],
        }
    }
    rule_list = rules.ensure_rules_config(data)
    assert rule_list == [{"name": "Happ"}]
    assert data["responseRules"]["settings"] == {"disableSubscriptionAccessByPath": True}


# --------------------------------------------------------------------------- #
# rule ordering — the panel matches top-down, first hit wins
# --------------------------------------------------------------------------- #


def _stock_config():
    """The rules Remnawave seeds itself, trimmed to what matters here."""
    return [
        {
            "name": "Browser Subscription",
            "enabled": True,
            "operator": "AND",
            "conditions": [
                {
                    "headerName": "accept",
                    "operator": "CONTAINS",
                    "value": "text/html",
                    "caseSensitive": True,
                }
            ],
            "responseType": "BROWSER",
        },
        {
            "name": "Fallback Base64",
            "description": "System critical: do not delete or disable this rule.",
            "enabled": True,
            "operator": "AND",
            "conditions": [],
            "responseType": "XRAY_BASE64",
        },
    ]


def test_is_catch_all_detects_the_conditionless_rule():
    browser, fallback = _stock_config()
    assert rules.is_catch_all(fallback)
    assert not rules.is_catch_all(browser)
    assert rules.is_catch_all({"name": "x"})  # conditions key absent entirely


def test_insert_rule_goes_above_the_catch_all():
    # Appending would put the rule after "Fallback Base64", which matches everything —
    # it would never be evaluated. This is the regression this test locks down.
    rule_list = _stock_config()
    new = {"name": "Happ"}
    assert rules.insert_rule(rule_list, new) == 1
    assert [r["name"] for r in rule_list] == ["Browser Subscription", "Happ", "Fallback Base64"]


def test_insert_rule_ignores_a_disabled_catch_all():
    rule_list = _stock_config()
    rule_list[1]["enabled"] = False
    assert rules.insert_rule(rule_list, {"name": "Happ"}) == 2  # nothing shadows it


def test_insert_rule_appends_when_there_is_no_catch_all():
    rule_list = [_stock_config()[0]]
    assert rules.insert_rule(rule_list, {"name": "Happ"}) == 1


def test_fallback_response_type_is_read_from_the_catch_all():
    assert rules.fallback_response_type(_stock_config()) == "XRAY_BASE64"

    custom = _stock_config()
    custom[1]["responseType"] = "XRAY_JSON"
    assert rules.fallback_response_type(custom) == "XRAY_JSON"

    assert rules.fallback_response_type([]) == "XRAY_BASE64"  # documented default
