"""Pure business logic for response rules.

This module is deliberately free of I/O (no network, no files). Every function
takes plain dicts/lists and returns plain data, which is exactly why it is the
easiest part of the project to unit-test — see tests/test_rules.py.
"""

from .logger import logger


def rule_matches(rule, keyword):
    """True if the rule's name contains ``keyword`` (case-insensitive)."""
    return keyword in (rule.get("name") or "").lower()


def upsert_header(headers, key, value):
    """Update a header value by key, or append it if the key is missing."""
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
    cleared) does not linger on an existing rule. A rule's own ``responseType`` is never
    touched — we keep whatever the user set. Returns the number of rules that were touched.
    """
    count = 0
    for rule in rules:
        if rule_matches(rule, keyword):
            modifications = rule.setdefault("responseModifications", {})
            headers = modifications.setdefault("headers", [])
            for key, value in kv_pairs:
                upsert_header(headers, key, value)
            for key in remove_keys:
                remove_header(headers, key)
            count += 1
    return count


def build_incy_rule(routing_link, autorouting_link, response_type):
    """Build a default INCY response rule that matches the Incy user-agent.

    The ``autorouting`` header is included only when ``autorouting_link`` is truthy;
    a falsy value means no real ``AUTOROUTING_URL`` is configured, so the rule ships
    the ``routing`` header alone.
    """
    headers = []
    if autorouting_link:
        headers.append({"key": "autorouting", "value": autorouting_link})
    headers.append({"key": "routing", "value": routing_link})
    return {
        "name": "Incy",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "CONTAINS",
                "value": "Incy",
                "caseSensitive": False,
            }
        ],
        "responseType": response_type,
        "responseModifications": {"headers": headers},
    }
