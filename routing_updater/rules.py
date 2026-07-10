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


def apply_headers_to_matching_rules(rules, keyword, kv_pairs):
    """Update the headers of every rule whose name looks like ``keyword``.

    A rule's own ``responseType`` is never touched — we keep whatever the user set.
    Returns the number of rules that were touched.
    """
    count = 0
    for rule in rules:
        if rule_matches(rule, keyword):
            modifications = rule.setdefault("responseModifications", {})
            headers = modifications.setdefault("headers", [])
            for key, value in kv_pairs:
                upsert_header(headers, key, value)
            count += 1
    return count


def build_incy_rule(routing_link, autorouting_link, response_type):
    """Build a default INCY response rule that matches the Incy user-agent."""
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
        "responseModifications": {
            "headers": [
                {"key": "autorouting", "value": autorouting_link},
                {"key": "routing", "value": routing_link},
            ]
        },
    }
