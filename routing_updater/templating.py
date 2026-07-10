"""Everything about the routing template artifact: loading, stamping, encoding, saving.

Loading and saving are I/O; stamping/encoding/link-building are pure transforms.
They live together because they all revolve around the same template document.
"""

import base64
import json
import os
import time

from .config import AUTOROUTING_URL, OUTPUT_PATH, TEMPLATE_PATH
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
    which is what non-RU deployments want out of the box.
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
    """Return the compact-JSON + Base64 representation of the template."""
    json_str = json.dumps(template, separators=(",", ":"))
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


def build_links(template):
    """Build the Happ/INCY deep-links from an (already stamped) template."""
    b64 = encode_template(template)
    return {
        "happ_routing": f"happ://routing/onadd/{b64}",
        "incy_routing": f"incy://routing/onadd/{b64}",
        "incy_autorouting": f"incy://autorouting/onadd/{AUTOROUTING_URL}",
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
