"""Docker HEALTHCHECK entry point.

Exits 0 while the service is cycling normally, and non-zero once the heartbeat has
gone stale — i.e. the main loop hasn't completed an iteration within one update
interval plus a grace margin. Run as ``python -m routing_updater.healthcheck``.

The heartbeat file is written by ``runtime.write_heartbeat`` after every loop
iteration, so a stuck or dead loop stops refreshing it and the container is reported
``unhealthy``.
"""

import os
import sys
import time

from .config import HEARTBEAT_PATH, UPDATE_INTERVAL

# Allow one full interval plus a 10% (min 120s) grace margin before we call it
# unhealthy — one slow or retried cycle must not flap the health status.
MAX_AGE_SECONDS = UPDATE_INTERVAL + max(120, UPDATE_INTERVAL // 10)


def is_healthy(now=None):
    """True if the heartbeat exists and is fresh enough."""
    now = time.time() if now is None else now
    try:
        age = now - os.path.getmtime(HEARTBEAT_PATH)
    except OSError:
        # No heartbeat yet (e.g. before the first cycle) — Docker ignores failures
        # during the configured start-period.
        return False
    return age <= MAX_AGE_SECONDS


def main():
    sys.exit(0 if is_healthy() else 1)


if __name__ == "__main__":
    main()
