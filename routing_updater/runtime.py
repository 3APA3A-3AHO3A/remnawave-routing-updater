"""Process-lifecycle helpers: signal handling and interruptible sleeping.

A single ``threading.Event`` is set by SIGTERM/SIGINT and checked by the main
loop and the retry backoff, so ``docker stop`` exits promptly instead of waiting
out a long sleep.
"""

import os
import signal
import threading
import time

from .config import HEARTBEAT_PATH
from .logger import logger

shutdown_event = threading.Event()


def write_heartbeat(path=None):
    """Touch the heartbeat file so the healthcheck knows the loop is alive.

    Never raises — a heartbeat write failure must not take the service down.
    """
    path = path or HEARTBEAT_PATH
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except Exception as e:
        logger.error(f"Failed to write heartbeat {path}: {e}")


def _handle_signal(signum, frame):
    logger.info(f"Received signal {signum}. Shutting down...")
    shutdown_event.set()


def install_signal_handlers():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def interruptible_sleep(seconds):
    """Sleep up to ``seconds``, waking early if a shutdown was requested.

    Returns True if it was interrupted by shutdown, False if it slept the full time.
    """
    return shutdown_event.wait(timeout=seconds)
