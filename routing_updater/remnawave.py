"""Remnawave API client — the single boundary that talks to the network.

Wrapping the HTTP calls in a small class does two things: it keeps every ``requests``
detail in one place, and it lets tests swap in a fake client with the same
``get_settings`` / ``patch_settings`` methods (see tests/test_core.py).

Version compatibility
---------------------
``GET``/``PATCH /api/subscription-settings`` exist unchanged on panel 2.x and 3.x, and
so does the ``responseRules`` object we write into. What 3.0.0 removed are the
dedicated subscription fields (``happRouting``, ``happAnnounce``, ``profileTitle``,
``supportLink``, ``profileUpdateInterval``, ``isProfileWebpageUrlEnabled``) — none of
which this updater touches any more. That is the whole reason one code path covers
both majors.
"""

import requests

from .config import API_TOKEN, PANEL_URL, REQUEST_TIMEOUT

# Fields that only ever existed on 2.x. Their presence in a GET response is the
# cheapest reliable version probe — no extra endpoint, no version string parsing.
V2_ONLY_FIELDS = ("happRouting", "happAnnounce", "profileTitle", "profileUpdateInterval")

# Keys PATCH /api/subscription-settings accepts on both majors and that we may send.
# Everything else in the GET response (createdAt, updatedAt, …) is read-only, so we
# never echo it back: the panel would ignore it at best and reject it at worst.
PATCHABLE_FIELDS = ("responseRules",)


def detect_major_version(settings):
    """Guess the panel major version from a subscription-settings payload.

    Returns 2, 3, or None when the payload is unusable. Purely informational: it
    drives log lines and the 2.x-only legacy cleanup, never the request body.
    """
    if not isinstance(settings, dict):
        return None
    if any(field in settings for field in V2_ONLY_FIELDS):
        return 2
    return 3


def build_patch_payload(settings, extra=None):
    """Build the smallest valid PATCH body from a (already mutated) settings object.

    Sending only ``uuid`` plus the fields we actually changed keeps the request valid
    across both majors and immune to future schema churn — a full round-trip of the GET
    response would carry read-only fields that a stricter validator could reject.
    """
    uuid = settings.get("uuid")
    if not uuid:
        raise ValueError("subscription settings response has no 'uuid' — cannot PATCH")

    payload = {"uuid": uuid}
    for field in PATCHABLE_FIELDS:
        if field in settings:
            payload[field] = settings[field]
    if extra:
        payload.update(extra)
    return payload


class RemnawaveClient:
    def __init__(self, panel_url=PANEL_URL, token=API_TOKEN, timeout=REQUEST_TIMEOUT):
        self.api_url = f"{panel_url}/api/subscription-settings"
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_settings(self):
        """GET the current subscription settings. Returns the ``response`` object."""
        resp = requests.get(self.api_url, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("response")

    def patch_settings(self, data):
        """PATCH a partial settings object (see ``build_patch_payload``)."""
        resp = requests.patch(self.api_url, headers=self.headers, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp
