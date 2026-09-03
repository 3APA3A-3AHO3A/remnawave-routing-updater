"""Configuration layer: reads everything from environment variables / .env.

Keeping all environment access in one place means the rest of the code never
touches ``os.getenv`` directly — it just imports typed constants from here.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


PANEL_URL = os.getenv("PANEL_URL", "http://remnawave:3000").rstrip("/")
API_TOKEN = os.getenv("API_TOKEN", "")

# ---- Panel major version ----
# "auto" (default) — detected from the shape of GET /api/subscription-settings.
# "2" / "3"        — forced, e.g. to make the startup log unambiguous.
#
# The updater only ever writes into ``responseRules``, and that part of the API is
# byte-for-byte identical on 2.x and 3.x. So this setting only affects warnings and
# the legacy cleanup below — never the payload we send.
PANEL_VERSION = os.getenv("PANEL_VERSION", "auto").strip().lower()

AUTOROUTING_URL = os.getenv("AUTOROUTING_URL", "https://example.com/routing.json")

# The autorouting link is considered configured only when a real URL is given.
# Empty or the example.com placeholder means "not set": INCY then runs on the
# routing header alone (like Happ), without shipping a broken autorouting header.
AUTOROUTING_ENABLED = bool(AUTOROUTING_URL) and "example.com" not in AUTOROUTING_URL
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL_SECONDS", 21600))

TEMPLATE_PATH = os.getenv("TEMPLATE_PATH", "/app/template.json")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "/app/output/routing.json")

# HTTP request timeout to the Remnawave API (seconds)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SECONDS", 30))

# Number of retries on a network error before falling back to the normal interval
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", 3))

# ---- Client support toggles ----
# Both clients are handled identically: the routing link goes into the headers of the
# matching Response Rule (SRR) and nowhere else. Nothing outside ``responseRules`` is
# touched — subscription settings, custom response headers, and every other header
# already present inside a rule are left exactly as the panel has them.
#
# Both default to on. Supporting a client the operator has no users on costs one extra
# response rule and zero requests, while an operator who *does* have such users gets
# working routing without reading the docs first.
ENABLE_HAPP = _as_bool(os.getenv("ENABLE_HAPP"), default=True)
ENABLE_INCY = _as_bool(os.getenv("ENABLE_INCY"), default=True)

# Substring used to find each client's rule (case-insensitive match on the rule name).
# Override if your rules are named something else, e.g. "Happ clients".
HAPP_RULE_MATCH = os.getenv("HAPP_RULE_MATCH", "happ").strip().lower()
INCY_RULE_MATCH = os.getenv("INCY_RULE_MATCH", "incy").strip().lower()

# When no matching rule exists at all, create a default one. Turn off if you would
# rather get a warning and add the rule yourself in the panel.
CREATE_MISSING_RULES = _as_bool(os.getenv("CREATE_MISSING_RULES"), default=True)

# responseType for AUTO-CREATED rules only. The responseType of a rule that already
# exists is never changed — whatever you set in the panel stays.
#
# Empty (the default) means "inherit": the type is copied from the panel's catch-all
# rule, i.e. the format these clients are already being served today. Creating the rule
# then changes nothing except adding the routing header. Set explicitly to override.
HAPP_RESPONSE_TYPE = os.getenv("HAPP_RESPONSE_TYPE", "").strip()
INCY_RESPONSE_TYPE = os.getenv("INCY_RESPONSE_TYPE", "").strip()

# ---- Legacy cleanup (panel 2.x only) ----
# On 2.x the panel still has the dedicated ``happRouting`` field, whose value is sent to
# Happ clients as a ``routing`` header. This updater no longer writes that field, so a
# leftover value is a second, stale source of routing. Enable to null it out once.
# On 3.x the field does not exist and this is a no-op.
CLEAR_LEGACY_HAPP_ROUTING = _as_bool(os.getenv("CLEAR_LEGACY_HAPP_ROUTING"), default=False)

# ---- Geo database mirror ----
# When enabled, the service downloads geoip.dat / geosite.dat to this server (next to
# routing.json) so clients where GitHub is blocked fetch them from your domain instead.
GEO_MIRROR_ENABLED = _as_bool(os.getenv("GEO_MIRROR_ENABLED"), default=False)

# Public URLs handed to clients (written into the template). If empty, the value from
# template.json is kept (GitHub) — so the default config keeps working where GitHub is reachable.
GEOIP_URL = os.getenv("GEOIP_URL", "").strip()
GEOSITE_URL = os.getenv("GEOSITE_URL", "").strip()

# Upstream the server pulls the databases from. Swap to a mirror if GitHub is ever
# unreachable from the server too.
GEOIP_SOURCE_URL = os.getenv(
    "GEOIP_SOURCE_URL",
    "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
)
GEOSITE_SOURCE_URL = os.getenv(
    "GEOSITE_SOURCE_URL",
    "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
)

# The .dat files and the state file live in the same directory as routing.json.
GEO_DIR = os.path.dirname(OUTPUT_PATH)
GEO_STATE_PATH = os.path.join(GEO_DIR, ".geo_state.json")

# Liveness heartbeat: touched after every completed loop iteration. The Docker
# HEALTHCHECK (see healthcheck.py) marks the container unhealthy if it goes stale.
HEARTBEAT_PATH = os.path.join(GEO_DIR, ".heartbeat")

# ---- Geo database trimming (server-side UseChunkFiles) ----
# When enabled, the full databases are downloaded to a private cache and only the
# categories referenced in the template are re-emitted into the served .dat files —
# so clients fetch a tiny file instead of the full ~10–17 MB. Needs GEO_MIRROR_ENABLED.
GEO_TRIM_ENABLED = _as_bool(os.getenv("GEO_TRIM_ENABLED"), default=False)

# Where the full (untrimmed) databases are cached — not served to clients.
GEO_CACHE_DIR = os.path.join(GEO_DIR, ".cache")

# ---- LastUpdated stamping mode ----
# "interval"      — bump LastUpdated every cycle (previous behaviour, default).
# "on_geo_change" — bump only when the mirrored database actually changed.
STAMP_MODE = os.getenv("STAMP_MODE", "interval").strip().lower()
