"""Statistical gates consume scored evidence; they never authorize release."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone

import pytest

from test_thermal_graduation_policy import inputs
from thermal_model.graduation_policy import derive_policy
from thermal_model import graduation_statistics as statistics


def assessment_inputs():
    values=inputs();values['intervals']['holdout_end']='2026-08-31T12:00:00+00:00'
    policy=derive_policy(**values)
    origin=datetime(2026,7,27,12,tzinfo=timezone.utc)
    rows=[]
    for day in range(35):
        issue=origin+timedelta(days=day)
        for hours in (1,6,12,24):
            sign=-1 if day%2 else 1
            rows.append(dict(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=hours)).isoformat(),
                horizon_hours=hours,regime='warm',artifact_sha256='a'*64,runtime_sha256='b'*64,
                sensor_epochs=deepcopy(policy['candidate']['sensor_epochs']),model_error_f=sign*.3,
                persistence_error_f=sign*2,recent_cycle_error_f=sign*3,
                interval_width_f=2,interval_covered=day>=3))
    return policy,rows,datetime(2026,8,31,13,tzinfo=timezone.utc)


def test_convincing_forecast_skill_does_not_require_action_labels():
    policy,rows,now=assessment_inputs()
    report=statistics.assess_predictive_skill(policy,rows,now=now)
    assert report['statistical_forecast_gates_passed'] is True
    assert report['release_authorized'] is False
    assert report['horizons']['24']['independent_windows']==35
    assert report['horizons']['24']['metrics']['model']['mae_f']==pytest.approx(.3)
    assert report['horizons']['24']['skill_upper_f']['persistence']<0
    assert report['horizons']['24']['skill_upper_f']['recent_cycle']<0
    assert report['action_evidence_evaluated'] is False


@pytest.mark.parametrize('damage',['baseline_loss','ties','poor_coverage','wide_interval','mixed_artifact',
    'mixed_runtime','epoch','overlap','sparse','stale','holdout_not_finished','future_training'])
def test_bad_or_insufficient_statistical_evidence_does_not_pass(damage):
    policy,rows,now=assessment_inputs()
    if damage=='baseline_loss':
        for row in rows:row['model_error_f']=4
    elif damage=='ties':
        for row in rows:row['model_error_f']=row['persistence_error_f']
    elif damage=='poor_coverage':
        for row in rows:row['interval_covered']=False
    elif damage=='wide_interval':
        for row in rows:row['interval_width_f']=30
    elif damage=='mixed_artifact':rows[0]['artifact_sha256']='d'*64
    elif damage=='mixed_runtime':rows[0]['runtime_sha256']='e'*64
    elif damage=='epoch':rows[0]['sensor_epochs']['air']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    elif damage=='overlap':
        for i,row in enumerate(rows):
            issue=datetime(2026,7,27,12,tzinfo=timezone.utc)+timedelta(seconds=i)
            row['issue_at']=issue.isoformat();row['target_at']=(issue+timedelta(hours=row['horizon_hours'])).isoformat()
    elif damage=='sparse':rows=rows[:4]
    elif damage=='stale':now+=timedelta(days=2)
    elif damage=='holdout_not_finished':now=datetime(2026,8,20,tzinfo=timezone.utc)
    elif damage=='future_training':rows[0]['issue_at']='2026-07-15T00:00:00+00:00'
    try:report=statistics.assess_predictive_skill(policy,rows,now=now)
    except ValueError:return
    assert report['statistical_forecast_gates_passed'] is False
    assert report['release_authorized'] is False


def test_density_cannot_change_a_daily_skill_confidence_bound():
    policy,rows,now=assessment_inputs()
    before=statistics.assess_predictive_skill(policy,rows,now=now)
    # An additional same-day 1h issue gets no new daily statistical weight.
    extra=deepcopy(rows[0]);issue=datetime.fromisoformat(extra['issue_at'])+timedelta(hours=2)
    extra.update(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=1)).isoformat())
    after=statistics.assess_predictive_skill(policy,[*rows,extra],now=now)
    assert before['horizons']['1']['independent_days']==after['horizons']['1']['independent_days']
    assert before['horizons']['1']['skill_upper_f']==after['horizons']['1']['skill_upper_f']


def test_fixed_holdout_remains_valid_when_fresh_prospective_outcomes_arrive():
    policy,rows,now=assessment_inputs()
    last=[deepcopy(row) for row in rows[-4:]]
    for day in range(1,11):
        for row in last:
            extended=deepcopy(row)
            extended['issue_at']=(datetime.fromisoformat(row['issue_at'])+timedelta(days=day)).isoformat()
            extended['target_at']=(datetime.fromisoformat(row['target_at'])+timedelta(days=day)).isoformat()
            extended['interval_covered']=True
            rows.append(extended)
    report=statistics.assess_predictive_skill(policy,rows,now=now+timedelta(days=10))
    assert report['statistical_forecast_gates_passed'] is True
    assert report['horizons']['24']['independent_windows']==35
    assert report['prospective']['24']['independent_windows']==45
    assert report['release_authorized'] is False
