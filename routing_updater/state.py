"""Tiny persistent state for the ``on_geo_change`` stamping mode.

Stores the last ``LastUpdated`` value (and an ``applied`` flag) in a small JSON file
next to routing.json, so that after a container restart the stamp does not jump and
force every client to re-download the databases needlessly.

Only used when ``STAMP_MODE == "on_geo_change"`` — the default ``interval`` mode does
no state I/O at all.
"""

import json
import os

from .config import GEO_STATE_PATH
from .logger import logger


def load_state(path=None):
    """Read the state dict. Returns ``{}`` if the file is missing or unreadable."""
    path = path or GEO_STATE_PATH
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state, path=None):
    """Persist the state dict atomically. Never raises — failure is logged only."""
    path = path or GEO_STATE_PATH
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"Failed to persist state {path}: {e}")
