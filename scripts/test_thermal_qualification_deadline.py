"""Publication validity is bounded by original outcome clocks, not cache age."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from thermal_model import graduation_decision as decision
from thermal_model.forcing_capture import _canonical
from test_thermal_graduation_decision import classifier_case
from test_thermal_graduation_policy import inputs

NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def source_rows():
    return [dict(issue_at=(NOW-timedelta(hours=hours+3)).isoformat(),
        target_at=(NOW-timedelta(hours=3)).isoformat(), horizon_hours=hours)
        for hours in (1, 6, 12, 24)]


def policy():
    from thermal_model.graduation_policy import derive_policy
    return derive_policy(**inputs())


def test_deadline_uses_least_recent_supported_horizon_outcome():
    rows = source_rows(); rows[-1]['target_at'] = (NOW-timedelta(hours=23)).isoformat()
    rows[-1]['issue_at'] = (NOW-timedelta(hours=47)).isoformat()
    assert decision.qualification_deadline(policy(), rows) == NOW+timedelta(hours=1)


def test_absent_horizon_and_nonprospective_rows_cannot_provide_deadline():
    rows = source_rows()
    assert decision.qualification_deadline(policy(), rows[:-1]) is None
    for row in rows: row['issue_at'] = '2026-06-01T00:00:00+00:00'
    assert decision.qualification_deadline(policy(), rows) is None


@pytest.mark.parametrize('legacy_schema',['v1','v2'])
def test_report_v3_preserves_source_deadline_and_refuses_legacy_shape(monkeypatch,legacy_schema):
    module, args = classifier_case(monkeypatch)
    report = module.qualify_candidate(**args)
    assert report['schema'] == 'earthship-thermal-qualification-report/v3'
    assert report['qualification_expires_at'] is not None
    report['schema'] = 'earthship-thermal-qualification-report/'+legacy_schema
    if legacy_schema=='v1':report.pop('qualification_expires_at')
    report['report_sha256'] = sha256(_canonical({key: value for key, value in report.items() if key != 'report_sha256'})).hexdigest()
    with pytest.raises(ValueError): module.validate_qualification_report(report)
