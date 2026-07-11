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
# Happ: updates the built-in happRouting field + any Happ-like response rule. On by default.
ENABLE_HAPP = _as_bool(os.getenv("ENABLE_HAPP"), default=True)

# INCY: updates any Incy-like rule, or creates a default one if missing. Off by default.
ENABLE_INCY = _as_bool(os.getenv("ENABLE_INCY"), default=False)

# responseType for the auto-created INCY rule only (XRAY_BASE64 is closest to the panel
# default). The responseType of rules that already exist is never changed.
INCY_RESPONSE_TYPE = os.getenv("INCY_RESPONSE_TYPE", "XRAY_BASE64")

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
