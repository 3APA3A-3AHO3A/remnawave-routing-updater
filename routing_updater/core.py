"""Orchestration: wire the pieces together into one update cycle.

``apply_changes`` is a pure transform (dict in, dict mutated, summary out), which
keeps the toggle logic unit-testable. ``update_routing`` adds the I/O around it:
load the template, save the file, talk to the API, retry on network errors.
"""

import time

import requests

from . import mirror, rules, state, templating
from .config import (
    ENABLE_HAPP,
    ENABLE_INCY,
    GEO_MIRROR_ENABLED,
    GEOIP_URL,
    GEOSITE_URL,
    INCY_RESPONSE_TYPE,
    RETRY_ATTEMPTS,
    STAMP_MODE,
)
from .logger import logger
from .runtime import interruptible_sleep, shutdown_event


def apply_changes(data, links, *, enable_happ, enable_incy, incy_response_type):
    """Mutate the settings ``data`` according to the toggles. Returns a summary list.

    Toggles are passed in explicitly (dependency injection) rather than read from
    the config module, so tests can exercise every combination without monkeypatching.
    """
    summary = []

    response_rules = data.get("responseRules")
    existing_rules = response_rules.get("rules", []) if isinstance(response_rules, dict) else []

    if enable_happ:
        # Built-in field — works out of the box even without any rule
        data["happRouting"] = links["happ_routing"]
        touched = rules.apply_headers_to_matching_rules(
            existing_rules, "happ", [("routing", links["happ_routing"])]
        )
        summary.append(f"Happ: field set, {touched} rule(s) updated")

    if enable_incy:
        incy_pairs = [
            ("routing", links["incy_routing"]),
            ("autorouting", links["incy_autorouting"]),
        ]
        touched = rules.apply_headers_to_matching_rules(existing_rules, "incy", incy_pairs)
        if touched == 0:
            # No Incy-like rule found — create a default one
            container = data.setdefault("responseRules", {})
            container.setdefault("version", "1")
            container.setdefault("rules", []).append(
                rules.build_incy_rule(
                    links["incy_routing"], links["incy_autorouting"], incy_response_type
                )
            )
            summary.append("Incy: no rule found — default rule created")
        else:
            summary.append(f"Incy: {touched} rule(s) updated")

    return summary


def decide_update(mode, geo_changed, state_data, now):
    """Decide the LastUpdated value and whether the panel must be patched (pure).

    Returns ``(last_updated, must_patch, new_state)``.

    * ``interval``      — stamp = now() every cycle, always patch (previous behaviour).
    * ``on_geo_change`` — stamp advances only when the database changed (or on the very
      first run); the panel is patched only then, so short intervals stay cheap.
    """
    new_state = dict(state_data)

    if mode == "on_geo_change":
        first_run = "last_updated" not in new_state
        if geo_changed or first_run:
            new_state["last_updated"] = str(int(now))
        last_updated = new_state["last_updated"]
        must_patch = bool(geo_changed) or not new_state.get("applied")
    else:  # "interval" (default)
        last_updated = str(int(now))
        must_patch = True

    return last_updated, must_patch, new_state


def update_routing(client):
    """Run one full update cycle against the given Remnawave client."""
    logger.info("Starting routing update...")

    template = templating.load_template()
    if not template:
        return

    # Refresh the local geo databases first, so the "re-download" signal we send to
    # clients points at an already up-to-date mirror. Without the mirror we cannot know
    # whether the database changed, so we treat every cycle as a change.
    geo_changed = mirror.mirror_geo_files() if GEO_MIRROR_ENABLED else True

    on_change = STAMP_MODE == "on_geo_change"
    state_data = state.load_state() if on_change else {}
    last_updated, must_patch, new_state = decide_update(
        STAMP_MODE, geo_changed, state_data, time.time()
    )

    templating.apply_overrides(template, GEOIP_URL, GEOSITE_URL)
    templating.stamp_template(template, last_updated)
    if not templating.save_output(template):
        return

    links = templating.build_links(template)

    if not must_patch:
        logger.info("Geo database unchanged — panel left untouched.")
        if on_change:
            state.save_state(new_state)
        return

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            data = client.get_settings()
            if not data:
                logger.error("API error: 'response' object not found in server response.")
                return

            summary = apply_changes(
                data,
                links,
                enable_happ=ENABLE_HAPP,
                enable_incy=ENABLE_INCY,
                incy_response_type=INCY_RESPONSE_TYPE,
            )

            client.patch_settings(data)
            if on_change:
                new_state["applied"] = True
                state.save_state(new_state)
            logger.info("✅ Remnawave database updated successfully! " + " | ".join(summary))
            return

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error while calling the Remnawave API: {e}")
            if getattr(e, "response", None) is not None:
                logger.error(f"Server response: {e.response.text}")

            if attempt < RETRY_ATTEMPTS and not shutdown_event.is_set():
                wait = 5 * attempt
                logger.info(f"Retrying in {wait} sec (attempt {attempt}/{RETRY_ATTEMPTS})...")
                interruptible_sleep(wait)
            else:
                logger.error("All attempts exhausted. Waiting for the next cycle.")
