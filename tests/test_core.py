"""Tests for the orchestration layer.

``apply_changes`` is tested directly (pure). ``update_routing`` is tested with a
fake client and monkeypatched template I/O — showing how the client boundary and
the I/O split make the orchestration testable without a network or real files.
"""

from routing_updater import core, templating

LINKS = {
    "happ_routing": "happ://routing/onadd/B64",
    "incy_routing": "incy://routing/onadd/B64",
    "incy_autorouting": "incy://autorouting/onadd/https://sub.example/routing.json",
}


def test_apply_changes_sets_happ_field():
    data = {}
    summary = core.apply_changes(
        data, LINKS, enable_happ=True, enable_incy=False, incy_response_type="XRAY_BASE64"
    )
    assert data["happRouting"] == LINKS["happ_routing"]
    assert any("Happ" in s for s in summary)


def test_apply_changes_creates_incy_rule_when_missing():
    data = {"happRouting": "z"}
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    created = data["responseRules"]["rules"][0]
    assert created["name"] == "Incy"
    assert created["responseType"] == "XRAY_BASE64"


def test_apply_changes_keeps_existing_incy_response_type():
    data = {
        "responseRules": {
            "version": "1",
            "rules": [{"name": "Incy", "responseType": "XRAY_JSON"}],
        }
    }
    core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=True, incy_response_type="XRAY_BASE64"
    )
    assert data["responseRules"]["rules"][0]["responseType"] == "XRAY_JSON"


def test_apply_changes_does_nothing_when_both_disabled():
    data = {"foo": "bar"}
    summary = core.apply_changes(
        data, LINKS, enable_happ=False, enable_incy=False, incy_response_type="XRAY_BASE64"
    )
    assert summary == []
    assert data == {"foo": "bar"}


class FakeClient:
    """Stands in for RemnawaveClient — same methods, no network."""

    def __init__(self, settings):
        self._settings = settings
        self.patched = None

    def get_settings(self):
        return self._settings

    def patch_settings(self, data):
        self.patched = data


def test_update_routing_pushes_patched_settings(monkeypatch):
    # Replace the file I/O so no real template or output file is needed.
    monkeypatch.setattr(templating, "load_template", lambda: {"Name": "T"})
    monkeypatch.setattr(templating, "save_output", lambda template: True)

    client = FakeClient({"happRouting": ""})
    core.update_routing(client)

    assert client.patched is not None
    assert client.patched["happRouting"].startswith("happ://routing/onadd/")
