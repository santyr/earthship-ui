import json
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

import pytest


def arguments():
    return dict(
        decision_id=UUID("00000000-0000-4000-8000-000000000001"),
        issued_at=datetime(2026, 9, 5, 12, 40, tzinfo=timezone.utc),
        site_timezone="America/Denver", source_revision="34ea969",
        policy_version="forecast-v3", bank_epoch="discover_4_module_2026",
        prediction_day=date(2026, 9, 5), advisory="vent_tonight",
        notification_eligible=False, notification_suppressed=False,
        inputs={
            "weather_today_high_raw_f": 91, "weather_today_low_raw_f": 49,
            "tomorrow_high_raw_f": 94, "tomorrow_low_raw_f": 48,
            "tomorrow_high_corrected_f": 90.25,
            "tomorrow_low_corrected_f": 40.125,
            "high_bias_f": 3.75, "low_bias_f": 7.875,
            "next_three_highs_raw_f": [94, 93, 92],
            "three_day_high_mean_corrected_f": 89.25,
            "pv_today_kwh": 6.3, "trough_tomorrow_pct": 86,
        },
        thresholds={"close_up_high_f": 95, "close_up_streak_f": 92,
                    "vent_high_f": 90, "trough_dm_pct": 30},
    )


def test_freezes_exact_inputs_and_separate_target_windows():
    from advisory_records import build_decision_record
    args = arguments()
    encoded = build_decision_record(**args)
    payload = json.loads(encoded)
    assert payload["schema_version"] == 1
    assert payload["record_type"] == "advisory_decision"
    assert payload["issued_at"] == "2026-09-05T12:40:00Z"
    assert payload["inputs"]["tomorrow_high_corrected_f"] == 90.25
    assert payload["inputs"]["tomorrow_low_corrected_f"] == 40.125
    assert payload["thresholds"] == args["thresholds"]
    targets = payload["targets"]
    assert targets["pv_today"]["start"] == "2026-09-05T06:00:00Z"
    assert targets["trough"]["start"] == "2026-09-06T02:00:00Z"
    assert targets["trough"]["end"] == "2026-09-06T17:00:00Z"
    assert targets["weather_tomorrow"]["start"] == "2026-09-06T06:00:00Z"
    assert targets["thermal_tomorrow"] == targets["weather_tomorrow"]
    assert targets["action_transition"] == targets["trough"]
    assert targets["weather_today"] == targets["pv_today"]
    assert payload["notification"] == {"eligible": False, "suppressed": False}
    args["inputs"]["next_three_highs_raw_f"][0] = 200
    args["thresholds"]["vent_high_f"] = 200
    payload["inputs"]["tomorrow_high_corrected_f"] = 200
    assert json.loads(encoded)["inputs"]["next_three_highs_raw_f"][0] == 94
    assert json.loads(encoded)["thresholds"]["vent_high_f"] == 90
    assert json.loads(encoded)["inputs"]["tomorrow_high_corrected_f"] == 90.25


def test_retry_is_canonical_but_new_invocation_has_new_identity():
    from advisory_records import build_decision_record
    args = arguments()
    original = build_decision_record(**args)
    args["inputs"] = dict(reversed(list(args["inputs"].items())))
    args["issued_at"] = args["issued_at"].astimezone(timezone(timedelta(hours=-6)))
    assert build_decision_record(**args) == original
    args["decision_id"] = UUID("00000000-0000-4000-8000-000000000002")
    assert build_decision_record(**args) != original


@pytest.mark.parametrize("key", ["tomorrow_high_corrected_f", "pv_today_kwh", "trough_tomorrow_pct"])
@pytest.mark.parametrize("bad", [None, True, "90", float("nan"), float("inf"), 10**1000])
def test_inputs_must_be_finite_numbers(key, bad):
    from advisory_records import build_decision_record
    args = arguments(); args["inputs"][key] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("container", ["inputs", "thresholds"])
def test_unknown_fields_are_not_a_freeform_private_data_channel(container):
    from advisory_records import build_decision_record
    args = arguments(); args[container]["message_body"] = "do not persist"
    with pytest.raises(ValueError):
        build_decision_record(**args)
    args = arguments(); args[container].pop(next(iter(args[container])))
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("bad", [[], [90, 91], [90, 91, 92, 93], [90, None, 92], [90, True, 92]])
def test_three_day_summary_requires_three_finite_inputs(bad):
    from advisory_records import build_decision_record
    args = arguments(); args["inputs"]["next_three_highs_raw_f"] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("field,bad", [
    ("decision_id", "not-a-uuid"), ("issued_at", datetime(2026, 9, 5)),
    ("prediction_day", datetime(2026, 9, 5, tzinfo=timezone.utc)),
    ("source_revision", ""), ("policy_version", "raw message text"),
    ("bank_epoch", ""), ("advisory", "invented_policy"),
    ("notification_eligible", 1), ("notification_suppressed", "false"),
])
def test_invalid_identity_and_policy_metadata_is_rejected(field, bad):
    from advisory_records import build_decision_record
    args = arguments(); args[field] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


def test_suppression_requires_eligibility_and_never_recomputes_category():
    from advisory_records import build_decision_record
    args = arguments(); args["notification_suppressed"] = True
    with pytest.raises(ValueError):
        build_decision_record(**args)
    args["notification_eligible"] = True
    args["advisory"] = "none"
    result = json.loads(build_decision_record(**args))
    assert result["advisory"] == "none"
    assert result["notification"] == {"eligible": True, "suppressed": True}


@pytest.mark.parametrize("kind,target,status", [
    ("publication", "Thermal_Advisory", "accepted"),
    ("publication", "Predicted_SoC_Trough_Tomorrow", "failed"),
    ("publication", "Predicted_SoC_Trough_Tomorrow", "unknown"),
    *[("notification", "deep_cycle_dm", s) for s in (
        "not_eligible", "suppressed", "attempted_reported_success",
        "attempted_failed", "attempted_unknown", "unknown")],
])
def test_result_states_preserve_observed_semantics(kind, target, status):
    from advisory_records import build_result_record
    args = dict(result_id=UUID("00000000-0000-4000-8000-000000000003"),
                decision_id=arguments()["decision_id"],
                observed_at=arguments()["issued_at"], kind=kind,
                target=target, status=status)
    encoded = build_result_record(**args)
    assert build_result_record(**args) == encoded
    payload = json.loads(encoded)
    assert payload["status"] == status
    assert payload["target"] == target
    assert set(payload) == {"schema_version", "record_type", "result_id",
                            "decision_id", "observed_at", "kind", "target", "status"}


@pytest.mark.parametrize("kind,target,status", [
    ("publication", "Thermal_Advisory", "delivered"),
    ("notification", "recipient-key", "attempted_reported_success"),
    ("notification", "deep_cycle_dm", "accepted"),
    ("actuator", "ShurefloPump_Power", "accepted"),
])
def test_results_reject_unapproved_targets_and_delivery_claims(kind, target, status):
    from advisory_records import build_result_record
    with pytest.raises(ValueError):
        build_result_record(result_id=arguments()["decision_id"],
                            decision_id=arguments()["decision_id"],
                            observed_at=arguments()["issued_at"],
                            kind=kind, target=target, status=status)
