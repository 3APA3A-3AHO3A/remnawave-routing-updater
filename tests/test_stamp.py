"""Tests for the pure stamping/patch decision (``core.decide_update``).

No I/O, no fixtures — just data in, data out, mirroring the project's DI style.
"""

from routing_updater import core


def test_interval_always_stamps_now_and_patches():
    last_updated, must_patch, _ = core.decide_update("interval", False, {}, 1000)
    assert last_updated == "1000"
    assert must_patch is True

    # Even with prior state, interval keeps stamping and patching every cycle.
    lu2, must2, _ = core.decide_update(
        "interval", False, {"last_updated": "5", "applied": True}, 2000
    )
    assert lu2 == "2000"
    assert must2 is True


def test_on_change_first_run_stamps_and_patches():
    last_updated, must_patch, new_state = core.decide_update("on_geo_change", False, {}, 1000)
    assert last_updated == "1000"  # first run is treated as a change
    assert must_patch is True
    assert new_state["last_updated"] == "1000"


def test_on_change_unchanged_keeps_stamp_and_skips_patch():
    prev = {"last_updated": "1000", "applied": True}
    last_updated, must_patch, new_state = core.decide_update("on_geo_change", False, prev, 5000)
    assert last_updated == "1000"  # stamp stays stable when nothing changed
    assert must_patch is False
    assert new_state["last_updated"] == "1000"


def test_on_change_changed_bumps_and_patches():
    prev = {"last_updated": "1000", "applied": True}
    last_updated, must_patch, _ = core.decide_update("on_geo_change", True, prev, 5000)
    assert last_updated == "5000"
    assert must_patch is True


def test_on_change_retries_patch_when_previously_unapplied():
    # File already carried a stamp but the panel patch never succeeded -> patch again.
    prev = {"last_updated": "1000"}
    last_updated, must_patch, _ = core.decide_update("on_geo_change", False, prev, 5000)
    assert last_updated == "1000"
    assert must_patch is True


def test_decide_update_does_not_mutate_input_state():
    prev = {"last_updated": "1000", "applied": True}
    core.decide_update("on_geo_change", True, prev, 9999)
    assert prev == {"last_updated": "1000", "applied": True}
