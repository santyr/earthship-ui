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


def test_soc_summary_exposes_same_issue_bank_coverage_and_used_dates():
    from datetime import datetime, date, timedelta, timezone
    from advisory_windows import trough_window
    from test_qualified_soc_forecast import evidence
    from earthship_energy.trough_assessment import assess_trough_measurement
    day=date(2026,9,20);window=trough_window(day,'America/Denver')
    issue=window.end+timedelta(minutes=1)
    rows=[(window.start+timedelta(minutes=i),evidence(window.start+timedelta(minutes=i),soc=80)) for i in range(900)]
    assessment=assess_trough_measurement(prediction_day=day,site_timezone='America/Denver',assessed_at=issue,observations=rows,epoch_start=window.start-timedelta(days=60))
    state={'soc_evidence_assessed_at':issue.isoformat(),'soc_night_evidence':{'2026-09-21':{'bank_epoch':'bank','assessment':assessment}}}
    before=deepcopy(state)
    soc=fi.prediction_learning_support(state,['2026-09-21'])['soc_trough']
    assert soc['model_kind']=='rolling_completed_night_heuristic'
    assert soc['trained_model'] is False
    assert soc['source_qualified_night_count']==1
    assert soc['sample_dates']==['2026-09-21']
    assert soc['bank_epochs']==['bank']
    assert soc['issue_origin']==issue.isoformat()
    assert soc['source_coverage']['2026-09-21']> .99
    assert soc['source_evidence_digests']['2026-09-21']==assessment['evidence_digest']
    assert state==before


def test_soc_source_summary_withholds_unproven_or_future_assessments():
    from datetime import datetime, date, timedelta, timezone
    from earthship_energy.trough_assessment import assess_trough_measurement
    from advisory_windows import trough_window
    from test_qualified_soc_forecast import evidence
    day=date(2026,9,20);window=trough_window(day,'America/Denver');issue=window.end+timedelta(minutes=1)
    rows=[(window.start+timedelta(minutes=i),evidence(window.start+timedelta(minutes=i))) for i in range(900)]
    assessment=assess_trough_measurement(prediction_day=day,site_timezone='America/Denver',assessed_at=issue,observations=rows,epoch_start=window.start-timedelta(days=60))
    for damage in ('missing','future','wrong_day','coverage','bank'):
        record={'bank_epoch':'bank','assessment':deepcopy(assessment)}
        if damage=='future':record['assessment']['assessed_at']=(issue+timedelta(seconds=1)).isoformat()
        if damage=='wrong_day':record['assessment']['prediction_day']='2026-09-19'
        if damage=='coverage':record['assessment']['coverage']=.5
        if damage=='bank':record['bank_epoch']=''
        records={} if damage=='missing' else {'2026-09-21':record}
        soc=fi.prediction_learning_support({'soc_evidence_assessed_at':issue.isoformat(),'soc_night_evidence':records},['2026-09-21'])['soc_trough']
        assert soc['source_qualified_night_count']==0
        assert soc['source_coverage']=={} and soc['bank_epochs']==[]
