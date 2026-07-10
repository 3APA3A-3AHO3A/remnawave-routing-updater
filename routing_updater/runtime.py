"""Process-lifecycle helpers: signal handling and interruptible sleeping.

A single ``threading.Event`` is set by SIGTERM/SIGINT and checked by the main
loop and the retry backoff, so ``docker stop`` exits promptly instead of waiting
out a long sleep.
"""

import signal
import threading

from .logger import logger

shutdown_event = threading.Event()


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
