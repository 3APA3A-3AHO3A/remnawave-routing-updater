"""Write a checksum sidecar next to each served geo database.

Happ fetches ``<url>.sha256`` for a custom geo URL and validates the downloaded file
against it; without a matching sidecar it reports *"geo files corrupted or missing"*.
Working custom/trimmed sources (e.g. roscomvpn-geosite) ship exactly such a file — its
content is the standard ``sha256sum`` line ``<hex>  <name>``.

Because a trimmed database's hash differs from the upstream's, we must compute the hash
of the file we actually serve. ``.sha256`` is what Happ requests; ``.sha256sum`` is written
too for tools that use that name.
"""

import hashlib
import os

from .logger import logger


def _sha256_hex(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_if_changed(path, content):
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == content:
                return False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
    return True


def write_sidecars(directory, names=("geoip.dat", "geosite.dat")):
    """Ensure ``<name>.sha256`` / ``<name>.sha256sum`` match each present database."""
    for name in names:
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            continue
        line = f"{_sha256_hex(path)}  {name}\n"  # GNU sha256sum format: "<hex>  <name>"
        wrote = _write_if_changed(path + ".sha256", line)
        wrote = _write_if_changed(path + ".sha256sum", line) or wrote
        if wrote:
            logger.info(f"{name}: checksum sidecar written.")
