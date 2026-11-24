"""Everything about the routing template artifact: loading, stamping, encoding, saving.

Loading and saving are I/O; stamping/encoding/link-building are pure transforms.
They live together because they all revolve around the same template document.
"""

import base64
import hashlib
import json
import os
import time

from .config import AUTOROUTING_ENABLED, AUTOROUTING_URL, OUTPUT_PATH, TEMPLATE_PATH
from .logger import logger


def load_template():
    """Read the routing template JSON from disk. Returns a dict, or None on failure."""
    try:
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read template {TEMPLATE_PATH}: {e}")
        return None


def apply_overrides(template, geoip_url="", geosite_url=""):
    """Point the geo-database URLs at your own mirror, if configured.

    Empty values are ignored, so the template keeps its built-in defaults (GitHub) —
    which is what the default deployment wants out of the box.
    """
    if geoip_url:
        template["Geoipurl"] = geoip_url
    if geosite_url:
        template["Geositeurl"] = geosite_url
    return template


def stamp_template(template, value=None):
    """Set ``LastUpdated``. Uses the current unix time unless ``value`` is given.

    This single field change is the whole trick: it makes the encoded payload
    differ, so clients treat the routing as updated and re-fetch fresh databases.
    Passing an explicit ``value`` lets the caller keep a stable stamp between cycles
    (see the ``on_geo_change`` mode in ``core``).
    """
    template["LastUpdated"] = value if value is not None else str(int(time.time()))
    return template


def encode_template(template):
    """Return the compact-JSON + Base64 representation of a template or profile."""
    json_str = json.dumps(template, separators=(",", ":"))
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


# Happ-style DNS types -> v2run DNS types.
_V2RUN_DNS_TYPES = {"doh": "DOH", "dou": "DOU", "dot": "DOT", "doq": "DOQ", "system": "SYSTEM"}
_V2RUN_ROUTE_GROUPS = ("BLOCK", "DIRECT", "PROXY")


def _as_flag(value):
    """Happ keeps booleans as strings ("true"/"false"); accept real booleans too."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _v2run_route_order(value):
    """``"block-proxy-direct"`` -> ``["BLOCK", "PROXY", "DIRECT"]``; None if unusable."""
    order = [part.strip().upper() for part in str(value or "").split("-") if part.strip()]
    if sorted(order) != sorted(_V2RUN_ROUTE_GROUPS):
        return None
    return order


def _v2run_dns_server(template, prefix):
    """One v2run DNS server (``remote`` / ``domestic``) from the Happ-style fields."""
    dns_type = _V2RUN_DNS_TYPES.get(str(template.get(f"{prefix}DNSType") or "").strip().lower())
    if not dns_type:
        return None
    if dns_type == "SYSTEM":
        return {"type": dns_type}
    domain = template.get(f"{prefix}DNSDomain") or ""
    ip = template.get(f"{prefix}DNSIP") or ""
    # Plain UDP needs an IP; the encrypted ones take the URL/host, falling back to the IP.
    address = ip if dns_type == "DOU" else (domain or ip)
    if not address:
        return None
    return {"type": dns_type, "address": address}


def _with_version(url, stamp):
    """Append ``v=<stamp>`` so a changed stamp is also a changed geo URL.

    The v2run profile has no ``LastUpdated``: the URL itself is the only thing the app
    can compare, so this is what tells it to fetch the databases again. The web server
    ignores the query string and serves the same static file.
    """
    if not url or not stamp:
        return url
    return f"{url}{'&' if '?' in url else '?'}v={stamp}"


_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def v2run_profile_id(name):
    """A stable profile ``id`` derived from the profile name (13 chars, ``[0-9a-z]``).

    v2run refuses a profile without ``id`` ("not a routing profile") and uses it to tell
    profiles apart: the same id on every update means the app refreshes the profile it
    already has instead of adding a new one. Deriving it from the name keeps it identical
    across cycles and restarts without storing anything; the shape matches the app's own
    ids (e.g. ``16n5gh5yi2wlu``).
    """
    number = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:9], "big")
    chars = []
    for _ in range(13):
        number, digit = divmod(number, 36)
        chars.append(_BASE36[digit])
    return "".join(chars)


def to_v2run_profile(template):
    """Convert the Happ-style template into a v2run routing profile (pure).

    Same rules, DNS and geo databases as every other client — just v2run's field names:
    ``RouteOrder`` becomes an array, the site/IP lists become ``direct``/``proxy``/``block``
    groups, the DNS servers become ``dns.remote``/``dns.domestic``. Empty groups and fields
    the template does not set are left out (optional in v2run), so the app keeps its own
    defaults there. ``id`` and ``name`` are always present: v2run rejects a profile
    without ``id``, although its documentation does not list the field.
    """
    name = template.get("Name") or "Routing"
    profile = {
        "id": v2run_profile_id(name),
        "name": name,
        "globalProxy": _as_flag(template.get("GlobalProxy", "true")),
    }

    route_order = _v2run_route_order(template.get("RouteOrder"))
    if route_order:
        profile["routeOrder"] = route_order
    if template.get("DomainStrategy"):
        profile["domainStrategy"] = template["DomainStrategy"]

    for group, sites_key, ips_key in (
        ("direct", "DirectSites", "DirectIp"),
        ("proxy", "ProxySites", "ProxyIp"),
        ("block", "BlockSites", "BlockIp"),
    ):
        rules = {}
        if template.get(sites_key):
            rules["sites"] = list(template[sites_key])
        if template.get(ips_key):
            rules["ips"] = list(template[ips_key])
        if rules:
            profile[group] = rules

    dns = {}
    remote = _v2run_dns_server(template, "Remote")
    if remote:
        dns["remote"] = remote
    domestic = _v2run_dns_server(template, "Domestic")
    if domestic:
        domestic["direct"] = True  # the domestic resolver is queried outside the tunnel
        dns["domestic"] = domestic
    if template.get("DnsHosts"):
        dns["hosts"] = dict(template["DnsHosts"])
    if "FakeDNS" in template:
        dns["fakeDns"] = _as_flag(template["FakeDNS"])
    if dns:
        profile["dns"] = dns

    stamp = template.get("LastUpdated")
    geo = {}
    if template.get("Geositeurl"):
        geo["geositeUrl"] = _with_version(template["Geositeurl"], stamp)
    if template.get("Geoipurl"):
        geo["geoipUrl"] = _with_version(template["Geoipurl"], stamp)
    if geo:
        profile["geo"] = geo

    return {"v2run": 1, "profile": profile}


def build_links(template):
    """Build the Happ/INCY/FixErrorVPN/v2run deep-links from an (already stamped) template.

    Happ, INCY and FixErrorVPN share one routing payload (the same Base64 string) — only
    the scheme differs. v2run reads its own profile format, converted from the same
    template by ``to_v2run_profile``. ``*_autorouting`` is ``None`` when no real
    ``AUTOROUTING_URL`` is configured, so callers skip the autorouting header instead of
    pointing clients at a placeholder.
    """
    b64 = encode_template(template)
    v2run_b64 = encode_template(to_v2run_profile(template))
    return {
        "happ_routing": f"happ://routing/onadd/{b64}",
        "incy_routing": f"incy://routing/onadd/{b64}",
        "incy_autorouting": (
            f"incy://autorouting/onadd/{AUTOROUTING_URL}" if AUTOROUTING_ENABLED else None
        ),
        "fixerrorvpn_routing": f"fixerrorvpn://routing/onadd/{b64}",
        "fixerrorvpn_autorouting": (
            f"fixerrorvpn://autorouting/onadd/{AUTOROUTING_URL}" if AUTOROUTING_ENABLED else None
        ),
        "v2run_routing": f"v2run://routing/onadd/{v2run_b64}",
    }


def save_output(template):
    """Write the template to OUTPUT_PATH (served to INCY autorouting). Returns bool."""
    try:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        logger.info(f"File {OUTPUT_PATH} saved successfully.")
        return True
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return False


def load_output(path=None):
    """Read back the routing.json we serve. Returns a dict, or None if unreadable.

    Used by the AUTOROUTING_URL preflight check to compare what we wrote against what
    the reverse proxy actually hands to clients.
    """
    try:
        with open(path or OUTPUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
