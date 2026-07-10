"""Remnawave API client — the single boundary that talks to the network.

Wrapping the two HTTP calls in a small class does two things: it keeps every
``requests`` detail in one place, and it lets tests swap in a fake client with
the same ``get_settings`` / ``patch_settings`` methods (see tests/test_core.py).
"""

import requests

from .config import API_TOKEN, PANEL_URL, REQUEST_TIMEOUT


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
        """PATCH the whole settings object back."""
        resp = requests.patch(self.api_url, headers=self.headers, json=data, timeout=self.timeout)
        resp.raise_for_status()
        return resp
