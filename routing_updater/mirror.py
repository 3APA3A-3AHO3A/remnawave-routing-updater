"""Geo database mirror: pull geoip.dat / geosite.dat to this server.

Clients where GitHub is blocked can then fetch the databases from your own domain
(next to routing.json) instead of ``github.com``. Downloads are:

* conditional (``If-None-Match`` / 304) so unchanged files are not re-fetched;
* atomic (write to ``.tmp`` then ``os.replace``) so the reverse proxy never serves a
  half-written file;
* fault-tolerant (a failed file is logged, not raised — clients keep the last copy).
"""

import os

import requests

from .config import GEO_DIR, GEOIP_SOURCE_URL, GEOSITE_SOURCE_URL, REQUEST_TIMEOUT
from .logger import logger


def default_sources():
    """Map of ``filename -> upstream URL`` to mirror."""
    return {
        "geoip.dat": GEOIP_SOURCE_URL,
        "geosite.dat": GEOSITE_SOURCE_URL,
    }


def _fetch_one(name, url, geo_dir, timeout):
    """Download one file if it changed upstream. Returns True if it was updated."""
    dest = os.path.join(geo_dir, name)
    etag_path = dest + ".etag"

    headers = {}
    if os.path.exists(etag_path):
        with open(etag_path, encoding="utf-8") as f:
            etag = f.read().strip()
        if etag:
            headers["If-None-Match"] = etag

    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 304:
        logger.info(f"{name}: unchanged (304)")
        return False
    resp.raise_for_status()

    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(resp.content)
    os.replace(tmp, dest)  # atomic: the proxy never sees a partial file

    new_etag = resp.headers.get("ETag")
    if new_etag:
        with open(etag_path, "w", encoding="utf-8") as f:
            f.write(new_etag)

    logger.info(f"{name}: updated ({len(resp.content)} bytes)")
    return True


def mirror_geo_files(geo_dir=None, sources=None, timeout=None):
    """Refresh every mirrored database. Returns True if at least one file changed."""
    geo_dir = geo_dir or GEO_DIR
    sources = sources if sources is not None else default_sources()
    timeout = timeout or REQUEST_TIMEOUT

    os.makedirs(geo_dir, exist_ok=True)
    changed = False
    for name, url in sources.items():
        try:
            if _fetch_one(name, url, geo_dir, timeout):
                changed = True
        except Exception as e:
            # Do not break the cycle: clients keep using the previous copy of the file.
            logger.error(f"Failed to mirror {name}: {e}")
    return changed
