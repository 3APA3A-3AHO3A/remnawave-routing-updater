"""Tests for the pure template transforms added for the geo mirror."""

from routing_updater import templating


def test_apply_overrides_sets_urls_when_given():
    template = {"Geoipurl": "gh_ip", "Geositeurl": "gh_site"}
    templating.apply_overrides(template, "https://d/geoip.dat", "https://d/geosite.dat")
    assert template["Geoipurl"] == "https://d/geoip.dat"
    assert template["Geositeurl"] == "https://d/geosite.dat"


def test_apply_overrides_keeps_defaults_when_empty():
    template = {"Geoipurl": "gh_ip", "Geositeurl": "gh_site"}
    templating.apply_overrides(template, "", "")
    assert template["Geoipurl"] == "gh_ip"
    assert template["Geositeurl"] == "gh_site"


def test_stamp_template_accepts_explicit_value():
    template = {}
    templating.stamp_template(template, "12345")
    assert template["LastUpdated"] == "12345"


def test_stamp_template_defaults_to_now():
    template = {}
    templating.stamp_template(template)
    assert template["LastUpdated"].isdigit()
