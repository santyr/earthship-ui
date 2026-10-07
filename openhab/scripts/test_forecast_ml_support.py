from copy import deepcopy

import forecast_intel as fi


def test_prediction_learning_support_counts_independent_days_without_mutation(monkeypatch):
    state = {
        "pv_score_evidence": {
            "2026-10-01": {"basis": "qualified_source_bound", "measured_kwh": 6.1},
            "2026-10-02": {"basis": "qualified_source_bound", "measured_kwh": 5.4},
            "2026-10-03": {"basis": "legacy_change_only", "measured_kwh": 4.9},
        },
        "hourly_temp_evidence_receipts": [
            {"target": "2026-10-01T12:00:00-06:00"},
            {"target": "2026-10-01T13:00:00-06:00"},
            {"target": "2026-10-02T12:00:00-06:00"},
        ],
        "hourly_temp_model": fi.hourly_model_seed(),
    }
    state["hourly_temp_model"]["12"]["count"] = 7
    state["hourly_temp_model"]["13"]["count"] = 3
    before = deepcopy(state)
    monkeypatch.setattr(fi, "PV_QUALIFIED_CALIBRATION_RELEASE", False)

    result = fi.prediction_learning_support(
        state, ["2026-09-30", "2026-09-29", "2026-09-28"]
    )

    assert result["soc_trough"]["unique_unit_count"] == 3
    assert result["soc_trough"]["minimum_unique_units_met"] is True
    assert result["pv_calibration"]["unique_unit_count"] == 2
    assert result["pv_calibration"]["active_parameter_count"] == 2
    assert result["pv_calibration"]["qualified_calibration_release_gate_open"] is False
    assert result["hourly_temperature"]["reported_unit_count"] == 3
    assert result["hourly_temperature"]["unique_unit_count"] == 2
    assert result["hourly_temperature"]["bucket_update_count"] == 10
    assert result["hourly_temperature"]["minimum_bucket_update_count"] == 0
    assert result["hourly_temperature"]["maximum_bucket_update_count"] == 7
    assert state == before


def test_prediction_learning_support_fails_closed_on_invalid_optional_state():
    state = {
        "pv_score_evidence": [],
        "hourly_temp_evidence_receipts": "invalid",
        "hourly_temp_model": {"12": {"count": True}},
    }
    result = fi.prediction_learning_support(state, [])
    assert result["soc_trough"]["unique_unit_count"] == 0
    assert result["soc_trough"]["minimum_unique_units_met"] is False
    assert result["pv_calibration"]["unique_unit_count"] == 0
    assert result["hourly_temperature"]["unique_unit_count"] == 0
    assert result["hourly_temperature"]["bucket_update_count"] == 0


def test_prediction_learning_support_quarantines_malformed_optional_origins():
    state = {
        "pv_score_evidence": {
            "not-a-date": {"basis": "qualified_source_bound", "measured_kwh": 5.0},
        },
        "hourly_temp_evidence_receipts": [
            {"target": "also-not-a-timestamp"},
        ],
        "hourly_temp_model": fi.hourly_model_seed(),
    }
    result = fi.prediction_learning_support(state, [])
    assert result["pv_calibration"]["status"] == "invalid_optional_state"
    assert result["pv_calibration"]["unique_unit_count"] == 0
    assert result["hourly_temperature"]["status"] == "invalid_optional_state"
    assert result["hourly_temperature"]["unique_unit_count"] == 0
