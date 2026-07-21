"""Focused tests for forecast_intel scoring idempotency (ML v3 data-quality fix).

Regression guard for the 2026-07-19 bug: main() scored yesterday on every
invocation with no guard, so N runs on one calendar day appended N duplicate
entries to the rolling error arrays, which would corrupt v3b conformal quantiles.
"""
import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "forecast_intel", os.path.join(os.path.dirname(__file__), "forecast_intel.py"))
fi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fi)


def test_should_score_day_fresh_state():
    # A day never scored before must be scored.
    assert fi.should_score_day({}, "2026-07-20") is True


def test_should_score_day_already_scored_today():
    # Re-running on the same calendar day must NOT re-score the same day.
    st = {"last_scored_day": "2026-07-20"}
    assert fi.should_score_day(st, "2026-07-20") is False


def test_should_score_day_new_day_after_prior():
    # A new day proceeds even though a prior day was scored.
    st = {"last_scored_day": "2026-07-19"}
    assert fi.should_score_day(st, "2026-07-20") is True


def test_five_reruns_append_exactly_one_error():
    # Simulate the exact 2026-07-19 failure: five runs scoring the same day.
    st = {"pv_errors": [], "last_scored_day": None}
    ykey = "2026-07-18"
    for _ in range(5):
        if fi.should_score_day(st, ykey):
            st["pv_errors"] = (st["pv_errors"] + [61.25])[-7:]
            st["last_scored_day"] = ykey
    assert st["pv_errors"] == [61.25], "re-runs must not duplicate the day's error"
