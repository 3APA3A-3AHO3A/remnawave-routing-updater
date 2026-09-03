"""Orchestration: wire the pieces together into one update cycle.

``apply_changes`` is a pure transform (dict in, dict mutated, summary out), which
keeps the toggle logic unit-testable. ``update_routing`` adds the I/O around it:
load the template, save the file, talk to the API, retry on network errors.
"""

import time

import requests

from . import checksums, geobuild, mirror, remnawave, rules, state, templating
from .config import (
    AUTOROUTING_ENABLED,
    AUTOROUTING_URL,
    CLEAR_LEGACY_HAPP_ROUTING,
    CREATE_MISSING_RULES,
    ENABLE_HAPP,
    ENABLE_INCY,
    GEO_CACHE_DIR,
    GEO_DIR,
    GEO_MIRROR_ENABLED,
    GEO_TRIM_ENABLED,
    GEOIP_URL,
    GEOSITE_URL,
    HAPP_RESPONSE_TYPE,
    HAPP_RULE_MATCH,
    INCY_RESPONSE_TYPE,
    INCY_RULE_MATCH,
    PANEL_VERSION,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    STAMP_MODE,
)
from .logger import logger
from .runtime import interruptible_sleep, shutdown_event


def _sync_client_rules(
    data, *, keyword, rule_name, user_agent, kv_pairs, remove_keys, response_type, create_missing
):
    """Write ``kv_pairs`` into every rule named like ``keyword``; create one if none exist.

    Returns a short summary string. The rules list is only materialised when a rule
    actually has to be created, so a panel with no matching rule and
    ``create_missing=False`` is left completely untouched.
    """
    container = data.get("responseRules")
    existing = container.get("rules", []) if isinstance(container, dict) else []
    touched = rules.apply_headers_to_matching_rules(
        existing, keyword, kv_pairs, remove_keys=remove_keys
    )

    if touched:
        return f"{rule_name}: {touched} rule(s) updated"

    if not create_missing:
        logger.warning(
            f"No response rule matching '{keyword}' found and rule creation is off — "
            f"{rule_name} routing was not delivered. Create the rule in the panel "
            f"(Subscription Settings -> Response Rules) or set CREATE_MISSING_RULES=true."
        )
        return f"{rule_name}: no rule found — skipped"

    rule_list = rules.ensure_rules_config(data)
    # An empty response_type means "keep serving what this client already gets" — we read
    # it off the catch-all rule so creating the rule changes nothing but the header.
    effective_type = response_type or rules.fallback_response_type(rule_list)
    position = rules.insert_rule(
        rule_list, rules.build_client_rule(rule_name, user_agent, kv_pairs, effective_type)
    )
    return (
        f"{rule_name}: no rule found — created at position {position + 1} "
        f"(responseType {effective_type})"
    )


def apply_changes(
    data,
    links,
    *,
    enable_happ,
    enable_incy,
    incy_autorouting=True,
    happ_response_type=HAPP_RESPONSE_TYPE,
    incy_response_type=INCY_RESPONSE_TYPE,
    happ_match=HAPP_RULE_MATCH,
    incy_match=INCY_RULE_MATCH,
    create_missing=CREATE_MISSING_RULES,
):
    """Mutate the settings ``data`` according to the toggles. Returns a summary list.

    Only ``data['responseRules']`` is ever written. The dedicated ``happRouting`` field
    is deliberately left alone: it is gone in panel 3.x, and even on 2.x writing both it
    and the rule header meant the same link was injected from two places. Happ and INCY
    are now handled identically — one routing header, inside the client's own rule.

    Toggles are passed in explicitly (dependency injection) rather than read from the
    config module, so tests can exercise every combination without monkeypatching.

    ``incy_autorouting`` (paired with a non-null ``links['incy_autorouting']``) controls
    whether the ``autorouting`` header is written. When no real ``AUTOROUTING_URL`` is
    configured, INCY ships the ``routing`` header alone — no broken autorouting link.
    """
    summary = []

    if enable_happ:
        summary.append(
            _sync_client_rules(
                data,
                keyword=happ_match,
                rule_name="Happ",
                user_agent="Happ",
                kv_pairs=[("routing", links["happ_routing"])],
                remove_keys=(),
                response_type=happ_response_type,
                create_missing=create_missing,
            )
        )

    if enable_incy:
        autorouting_link = links.get("incy_autorouting") if incy_autorouting else None
        kv_pairs = [("routing", links["incy_routing"])]
        remove_keys = ()
        if autorouting_link:
            kv_pairs.append(("autorouting", autorouting_link))
        else:
            # Not configured — strip any stale autorouting header left on existing rules.
            remove_keys = ("autorouting",)

        note = "" if autorouting_link else " (routing only, autorouting skipped)"
        summary.append(
            _sync_client_rules(
                data,
                keyword=incy_match,
                rule_name="Incy",
                user_agent="Incy",
                kv_pairs=kv_pairs,
                remove_keys=remove_keys,
                response_type=incy_response_type,
                create_missing=create_missing,
            )
            + note
        )

    return summary


def legacy_happ_cleanup(data, major_version, enabled=CLEAR_LEGACY_HAPP_ROUTING):
    """Return the extra PATCH fields needed to retire the 2.x ``happRouting`` field.

    On 2.x the panel sends ``happRouting`` to Happ clients as a ``routing`` header of its
    own. Since the updater no longer refreshes that field, a leftover value is a second,
    stale source of routing — so we offer to null it once. Returns ``{}`` when there is
    nothing to do (3.x, already empty, or the cleanup is switched off).
    """
    if major_version != 2 or not data.get("happRouting"):
        return {}

    if not enabled:
        logger.warning(
            "Panel 2.x still has a value in the legacy 'happRouting' field. It is sent to "
            "Happ clients as a second 'routing' header and this updater no longer keeps it "
            "fresh. Clear it in the panel, or set CLEAR_LEGACY_HAPP_ROUTING=true."
        )
        return {}

    logger.info("Clearing the legacy 'happRouting' field (CLEAR_LEGACY_HAPP_ROUTING=true).")
    data["happRouting"] = None
    return {"happRouting": None}


def resolve_major_version(settings, configured=PANEL_VERSION):
    """Pick the panel major version: an explicit PANEL_VERSION wins over detection."""
    if configured in ("2", "3"):
        return int(configured)
    if configured not in ("auto", ""):
        logger.warning(
            f"Unknown PANEL_VERSION '{configured}' — falling back to auto-detection. "
            "Valid values: auto, 2, 3."
        )
    return remnawave.detect_major_version(settings)


def verify_autorouting_url(url=AUTOROUTING_URL, timeout=REQUEST_TIMEOUT):
    """One-shot check that AUTOROUTING_URL really serves the routing.json we just wrote.

    Misconfiguring the reverse proxy is the single most common way to get stuck: the
    service happily reports success while INCY clients silently fetch a 404. Comparing
    the served ``LastUpdated`` against the local one turns that into one clear log line.
    Never raises and never blocks the loop — it only warns.
    """
    local = templating.load_output()
    if local is None:
        return None  # nothing written yet, nothing to compare

    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as e:
        logger.warning(
            f"AUTOROUTING_URL check: {url} is not reachable from this container ({e}). "
            "If your reverse proxy is only reachable from outside, ignore this — "
            "otherwise INCY clients will not get the routing profile either."
        )
        return False

    if resp.status_code != 200:
        logger.warning(
            f"AUTOROUTING_URL check: {url} returned HTTP {resp.status_code}. The reverse "
            "proxy is not serving routing.json — see the reverse proxy section of the README."
        )
        return False

    try:
        served = resp.json()
    except ValueError:
        logger.warning(
            f"AUTOROUTING_URL check: {url} did not return JSON. It is probably pointing at "
            "your subscription page instead of the served routing.json file."
        )
        return False

    if served.get("LastUpdated") != local.get("LastUpdated"):
        logger.warning(
            f"AUTOROUTING_URL check: {url} is reachable but serves a different/older file "
            f"(LastUpdated {served.get('LastUpdated')} vs local {local.get('LastUpdated')}). "
            "Check that the proxy points at the same volume this container writes to."
        )
        return False

    logger.info(f"AUTOROUTING_URL check: {url} serves the current routing.json. ✅")
    return True


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

    # Happ and INCY both validate each served database against a <file>.sha256 sidecar
    # (a trimmed file's hash differs from upstream's, so we publish the hash of what we serve).
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

            major = resolve_major_version(data)
            logger.info(f"Panel API detected as v{major}.x" if major else "Panel version unknown")

            summary = apply_changes(
                data,
                links,
                enable_happ=ENABLE_HAPP,
                enable_incy=ENABLE_INCY,
                incy_autorouting=AUTOROUTING_ENABLED,
            )
            extra = legacy_happ_cleanup(data, major)

            client.patch_settings(remnawave.build_patch_payload(data, extra))
            if on_change:
                new_state["applied"] = True
                state.save_state(new_state)
            logger.info("✅ Remnawave database updated successfully! " + " | ".join(summary))
            return

        except ValueError as e:
            # Malformed settings payload — retrying will not help.
            logger.error(f"❌ Unexpected API response: {e}")
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
