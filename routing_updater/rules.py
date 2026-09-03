"""Pure business logic for response rules.

This module is deliberately free of I/O (no network, no files). Every function
takes plain dicts/lists and returns plain data, which is exactly why it is the
easiest part of the project to unit-test — see tests/test_rules.py.

Everything the updater writes lives inside ``responseRules``. That container has the
same shape on panel 2.x and 3.x, which is what makes the updater version-agnostic.
"""

from .logger import logger

# The only config version the panel accepts today (RESPONSE_RULES_CONFIG_VERSION).
RESPONSE_RULES_VERSION = "1"


def rule_matches(rule, keyword):
    """True if the rule's name contains ``keyword`` (case-insensitive)."""
    if not isinstance(rule, dict):
        return False
    return keyword in (rule.get("name") or "").lower()


def upsert_header(headers, key, value):
    """Update a header value by key, or append it if the key is missing.

    Headers we do not manage (``support-email``, ``announce-url``, whatever else you
    set in the panel) are never read, reordered or dropped — only our own key is
    rewritten in place.
    """
    for header in headers:
        if header.get("key") == key:
            header["value"] = value
            return
    headers.append({"key": key, "value": value})
    logger.info(f"Header '{key}' was missing from the rule — added automatically.")


def remove_header(headers, key):
    """Drop every header with the given key. Returns True if anything was removed."""
    before = len(headers)
    headers[:] = [h for h in headers if h.get("key") != key]
    removed = len(headers) < before
    if removed:
        logger.info(f"Header '{key}' removed from the rule (no longer configured).")
    return removed


def apply_headers_to_matching_rules(rules, keyword, kv_pairs, remove_keys=()):
    """Update the headers of every rule whose name looks like ``keyword``.

    ``kv_pairs`` are upserted; any key in ``remove_keys`` is stripped afterwards, so a
    header that is no longer configured (e.g. ``autorouting`` once ``AUTOROUTING_URL`` is
    cleared) does not linger on an existing rule. A rule's own ``responseType``,
    ``conditions``, ``enabled`` flag and unrelated headers are never touched.
    Returns the number of rules that were modified.
    """
    count = 0
    for rule in rules:
        if not rule_matches(rule, keyword):
            continue

        modifications = rule.get("responseModifications")
        if not isinstance(modifications, dict):
            modifications = {}
            rule["responseModifications"] = modifications

        headers = modifications.get("headers")
        if not isinstance(headers, list):
            headers = []
            modifications["headers"] = headers

        for key, value in kv_pairs:
            upsert_header(headers, key, value)
        for key in remove_keys:
            remove_header(headers, key)

        if rule.get("enabled") is False:
            logger.warning(
                f"Rule '{rule.get('name')}' is disabled in the panel — headers were "
                "refreshed, but the panel will not apply them until you enable it."
            )
        count += 1
    return count


def ensure_rules_config(data):
    """Return the mutable ``rules`` list of ``data['responseRules']``, creating it if needed.

    ``responseRules`` may legitimately be ``null`` (a panel that has never had a rule),
    so a plain ``setdefault`` is not enough — a ``None`` value has to be replaced with a
    fresh, schema-valid container.
    """
    container = data.get("responseRules")
    if not isinstance(container, dict):
        container = {}
        data["responseRules"] = container

    if not container.get("version"):
        container["version"] = RESPONSE_RULES_VERSION

    rules = container.get("rules")
    if not isinstance(rules, list):
        rules = []
        container["rules"] = rules

    return rules


def is_catch_all(rule):
    """True if the rule matches every request, i.e. it has no conditions.

    The panel's own comment says it best: "Assuming that if there are no conditions, the
    rule should be matched". The stock config ships exactly such a rule at the bottom —
    ``Fallback Base64``, flagged *system critical* — and it is why appending is wrong.
    """
    if not isinstance(rule, dict):
        return False
    return not rule.get("conditions")


def find_catch_all(rule_list):
    """Return the first enabled catch-all rule, or None."""
    for rule in rule_list:
        if isinstance(rule, dict) and rule.get("enabled", True) and is_catch_all(rule):
            return rule
    return None


def fallback_response_type(rule_list, default="XRAY_BASE64"):
    """The responseType a client currently gets when no specific rule matches it.

    Creating our rule with this exact type is what makes auto-creation behaviour-neutral:
    the client keeps receiving the same subscription format it received yesterday, and the
    only thing that changes is the added ``routing`` header.
    """
    catch_all = find_catch_all(rule_list)
    if catch_all and catch_all.get("responseType"):
        return catch_all["responseType"]
    return default


def insert_rule(rule_list, new_rule):
    """Insert ``new_rule`` where it will actually be evaluated. Returns its index.

    Rules are matched top-down and the first hit wins, so a rule appended *after* the
    catch-all can never match — it would be dead config. We therefore insert directly
    above the first catch-all, and only fall back to appending when there is none.
    """
    for index, rule in enumerate(rule_list):
        if isinstance(rule, dict) and rule.get("enabled", True) and is_catch_all(rule):
            rule_list.insert(index, new_rule)
            return index
    rule_list.append(new_rule)
    return len(rule_list) - 1


def build_client_rule(name, user_agent_value, headers, response_type):
    """Build a default response rule matching a client by its user-agent.

    ``headers`` is a list of ``(key, value)`` pairs; pairs with a falsy value are
    skipped, so an unconfigured ``autorouting`` link yields no header at all rather
    than an empty one.
    """
    return {
        "name": name,
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "CONTAINS",
                "value": user_agent_value,
                "caseSensitive": False,
            }
        ],
        "responseType": response_type,
        "responseModifications": {
            "headers": [{"key": key, "value": value} for key, value in headers if value]
        },
    }
