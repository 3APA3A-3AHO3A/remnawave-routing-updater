"""Entry point: thin wiring only. Run with ``python -m routing_updater``.

Keeping the entry point tiny (startup checks + the loop) is what lets the rest of
the package be imported and tested without ever starting the service.
"""

from .config import (
    API_TOKEN,
    AUTOROUTING_URL,
    ENABLE_HAPP,
    ENABLE_INCY,
    GEO_MIRROR_ENABLED,
    GEO_TRIM_ENABLED,
    GEOIP_URL,
    GEOSITE_URL,
    PANEL_URL,
    STAMP_MODE,
    UPDATE_INTERVAL,
)
from .core import update_routing
from .logger import logger
from .remnawave import RemnawaveClient
from .runtime import install_signal_handlers, interruptible_sleep, shutdown_event


def main():
    install_signal_handlers()

    if not API_TOKEN:
        logger.error("CRITICAL ERROR: API_TOKEN is not set in .env!")
        raise SystemExit(1)

    if not ENABLE_HAPP and not ENABLE_INCY:
        logger.error(
            "CRITICAL ERROR: both ENABLE_HAPP and ENABLE_INCY are disabled. "
            "Enable at least one in .env!"
        )
        raise SystemExit(1)

    if ENABLE_INCY and "example.com" in AUTOROUTING_URL:
        logger.warning(
            "AUTOROUTING_URL not changed (using example.com). "
            "Set a real link in .env for INCY clients, otherwise autorouting won't work!"
        )

    if STAMP_MODE not in ("interval", "on_geo_change"):
        logger.warning(
            f"Unknown STAMP_MODE '{STAMP_MODE}' — falling back to 'interval'. "
            "Valid values: interval, on_geo_change."
        )

    if GEO_MIRROR_ENABLED and not (GEOIP_URL and GEOSITE_URL):
        logger.warning(
            "GEO_MIRROR_ENABLED is on but GEOIP_URL/GEOSITE_URL are empty — "
            "clients will still be told to download from the template's default URLs. "
            "Set both to your own domain so clients use the mirror."
        )

    if STAMP_MODE == "on_geo_change" and not GEO_MIRROR_ENABLED:
        logger.warning(
            "STAMP_MODE=on_geo_change without GEO_MIRROR_ENABLED: change cannot be "
            "detected, so every cycle counts as a change (same as 'interval')."
        )

    if GEO_TRIM_ENABLED and not GEO_MIRROR_ENABLED:
        logger.warning(
            "GEO_TRIM_ENABLED needs GEO_MIRROR_ENABLED (it trims the mirrored full "
            "databases) — trimming will be skipped until the mirror is enabled."
        )

    logger.info(
        f"Service started. Interval: {UPDATE_INTERVAL} sec. | API: {PANEL_URL} | "
        f"Happ: {'on' if ENABLE_HAPP else 'off'}, Incy: {'on' if ENABLE_INCY else 'off'} | "
        f"Geo mirror: {'on' if GEO_MIRROR_ENABLED else 'off'}"
        f"{' (trimmed)' if GEO_MIRROR_ENABLED and GEO_TRIM_ENABLED else ''}, "
        f"Stamp: {STAMP_MODE}"
    )

    client = RemnawaveClient()
    while not shutdown_event.is_set():
        update_routing(client)
        if shutdown_event.is_set():
            break
        logger.info(f"Waiting {UPDATE_INTERVAL} seconds...\n")
        interruptible_sleep(UPDATE_INTERVAL)

    logger.info("Service stopped gracefully.")


if __name__ == "__main__":
    main()
