"""Orchestration: wire the pieces together into one update cycle.

``apply_changes`` is a pure transform (dict in, dict mutated, summary out), which
keeps the toggle logic unit-testable. ``update_routing`` adds the I/O around it:
load the template, save the file, talk to the API, retry on network errors.
"""

import time

import requests

from . import checksums, geobuild, mirror, rules, state, templating
from .config import (
    AUTOROUTING_ENABLED,
    ENABLE_HAPP,
    ENABLE_INCY,
    GEO_CACHE_DIR,
    GEO_DIR,
    GEO_MIRROR_ENABLED,
    GEO_TRIM_ENABLED,
    GEOIP_URL,
    GEOSITE_URL,
    INCY_RESPONSE_TYPE,
    RETRY_ATTEMPTS,
    STAMP_MODE,
)
from .logger import logger
from .runtime import interruptible_sleep, shutdown_event


def apply_changes(
    data, links, *, enable_happ, enable_incy, incy_response_type, incy_autorouting=True
):
    """Mutate the settings ``data`` according to the toggles. Returns a summary list.

    Toggles are passed in explicitly (dependency injection) rather than read from
    the config module, so tests can exercise every combination without monkeypatching.

    ``incy_autorouting`` (paired with a non-null ``links['incy_autorouting']``) controls
    whether the ``autorouting`` header is written. When no real ``AUTOROUTING_URL`` is
    configured, INCY ships the ``routing`` header alone — no broken autorouting link.
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
        autorouting_link = links.get("incy_autorouting") if incy_autorouting else None
        incy_pairs = [("routing", links["incy_routing"])]
        remove_keys = ()
        if autorouting_link:
            incy_pairs.append(("autorouting", autorouting_link))
        else:
            # Not configured — strip any stale autorouting header left on existing rules.
            remove_keys = ("autorouting",)
        touched = rules.apply_headers_to_matching_rules(
            existing_rules, "incy", incy_pairs, remove_keys=remove_keys
        )
        auto_note = "" if autorouting_link else " (routing only, autorouting skipped)"
        if touched == 0:
            # No Incy-like rule found — create a default one
            container = data.setdefault("responseRules", {})
            container.setdefault("version", "1")
            container.setdefault("rules", []).append(
                rules.build_incy_rule(
                    links["incy_routing"], autorouting_link, incy_response_type
                )
            )
            summary.append(f"Incy: no rule found — default rule created{auto_note}")
        else:
            summary.append(f"Incy: {touched} rule(s) updated{auto_note}")

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


def refresh_geo(template):
    """Refresh the served geo databases. Returns True if a served file changed.

    * mirror only  — download the full .dat straight into the served directory.
    * mirror + trim — download the full .dat into a private cache, then re-emit only the
      categories the template uses into the served .dat (server-side ``UseChunkFiles``).
      "Changed" then means the *trimmed output* changed, i.e. the upstream database or the
      template's category set changed.
    * no mirror    — nothing to detect, so every cycle counts as a change.
    """
    if not GEO_MIRROR_ENABLED:
        return True

    if not GEO_TRIM_ENABLED:
        changed = mirror.mirror_geo_files()
    else:
        mirror.mirror_geo_files(geo_dir=GEO_CACHE_DIR)  # full -> private cache
        site_categories, ip_categories = geobuild.categories_from_template(template)
        changed = geobuild.trim_all(GEO_CACHE_DIR, GEO_DIR, site_categories, ip_categories)

    # Happ validates each served database against a <file>.sha256 sidecar (a trimmed
    # file's hash differs from upstream's, so we must publish the hash of what we serve).
    checksums.write_sidecars(GEO_DIR)
    return changed


def update_routing(client):
    """Run one full update cycle against the given Remnawave client."""
    logger.info("Starting routing update...")

    template = templating.load_template()
    if not template:
        return

    # Refresh the local geo databases first, so the "re-download" signal we send to
    # clients points at an already up-to-date mirror.
    geo_changed = refresh_geo(template)

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
                incy_autorouting=AUTOROUTING_ENABLED,
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
