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


def extended_operational_history(*,recent_loss):
    policy,initial,_=assessment_inputs();rows=deepcopy(initial)
    start=datetime.fromisoformat(initial[0]['issue_at'])
    for day in range(35,385):
        bad=recent_loss and day>=350
        for template in initial[:4]:
            row=deepcopy(template);issue=start+timedelta(days=day)
            sign=-1 if day%2 else 1
            row.update(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=row['horizon_hours'])).isoformat(),
                model_error_f=sign*(4 if bad else .3),interval_covered=not bad and (recent_loss or day%10!=0))
            rows.append(row)
    now=start+timedelta(days=385,hours=1)
    return policy,rows,now


def test_sustained_recent_loss_is_not_hidden_by_successful_pooled_history():
    policy,rows,now=extended_operational_history(recent_loss=True)
    historical=statistics.assess_predictive_skill(policy,rows,now=now)
    assert historical['statistical_forecast_gates_passed'] is True
    current=statistics.assess_current_predictive_skill(policy,rows,now=now)
    assert current['schema']=='earthship-thermal-statistical-assessment/v2'
    assert current['historical_assessment']==historical
    assert current['statistical_forecast_gates_passed'] is False
    recent=current['recent_prospective']['24']
    assert recent['independent_days']==35
    assert recent['metrics']['model']['mae_f']==4
    assert recent['gates']['persistence_skill'] is False
    assert recent['gates']['recent_cycle_skill'] is False
    assert recent['gates']['interval_calibration'] is False
    assert current['release_authorized'] is False


def test_recent_success_and_independent_sampling_preserve_qualification():
    policy,rows,now=extended_operational_history(recent_loss=False)
    before=statistics.assess_current_predictive_skill(policy,rows,now=now)
    assert before['statistical_forecast_gates_passed'] is True
    extra=deepcopy(rows[-4]);issue=datetime.fromisoformat(extra['issue_at'])+timedelta(hours=2)
    extra.update(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=1)).isoformat(),model_error_f=999)
    after=statistics.assess_current_predictive_skill(policy,[*rows,extra],now=now)
    assert after['recent_prospective']['1']==before['recent_prospective']['1']
    assert after['recent_prospective_by_regime']['24']['warm']['independent_days']==35


def test_recent_monitor_rejects_mixed_identity_instead_of_discarding_bad_rows():
    policy,rows,now=extended_operational_history(recent_loss=False)
    rows[-1]['artifact_sha256']='f'*64
    with pytest.raises(ValueError):statistics.assess_current_predictive_skill(policy,rows,now=now)


def test_recent_calibration_failure_with_good_skill_is_not_hidden_by_history():
    policy,rows,now=extended_operational_history(recent_loss=True)
    first_recent=datetime.fromisoformat(rows[-4]['issue_at'])-timedelta(days=34)
    for row in rows:
        if datetime.fromisoformat(row['issue_at'])>=first_recent:
            row['model_error_f']=.3;row['interval_width_f']=.2
    assert statistics.assess_predictive_skill(policy,rows,now=now)['statistical_forecast_gates_passed'] is True
    current=statistics.assess_current_predictive_skill(policy,rows,now=now)
    gates=current['recent_prospective']['24']['gates']
    assert gates['persistence_skill'] and gates['recent_cycle_skill']
    assert gates['interval_calibration'] is False
    assert current['statistical_forecast_gates_passed'] is False


def test_regime_specific_recent_loss_closes_gate_when_recent_horizon_passes():
    values=inputs();warm=deepcopy(values['development']);winter=deepcopy(warm)
    for row in winter:
        for field in ('issue_at','target_at'):row[field]=(datetime.fromisoformat(row[field])-timedelta(days=35)).isoformat()
        row['regime']='winter'
    values['development']=[*winter,*warm];values['regimes']=['warm','winter']
    values['intervals']['development_start']='2026-04-27T00:00:00+00:00'
    values['intervals']['holdout_end']='2026-10-05T12:00:00+00:00'
    policy=derive_policy(**values)
    _,templates,_=extended_operational_history(recent_loss=False)
    origin=datetime.fromisoformat(templates[0]['issue_at']);rows=[]
    for index,template in enumerate(templates):
        day=index//4
        for offset,regime in enumerate(('warm','winter')):
            row=deepcopy(template);issue=origin+timedelta(days=2*day+offset)
            row.update(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=row['horizon_hours'])).isoformat(),regime=regime)
            if regime=='winter' and day>=350:
                row['model_error_f']=(-1 if day%2 else 1)*2
                row['interval_width_f']=4
            rows.append(row)
    now=origin+timedelta(days=770,hours=1)
    current=statistics.assess_current_predictive_skill(policy,rows,now=now)
    assert current['historical_assessment']['statistical_forecast_gates_passed'] is True
    assert current['recent_prospective']['24']['statistical_gates_passed'] is True
    assert current['recent_prospective_by_regime']['24']['warm']['statistical_gates_passed'] is True
    assert current['recent_prospective_by_regime']['24']['winter']['gates']['persistence_skill'] is False
    assert current['statistical_forecast_gates_passed'] is False


@pytest.mark.parametrize('damage',['stale','sparse'])
def test_recent_monitor_reports_missing_support_or_freshness(damage):
    policy,rows,now=assessment_inputs()
    if damage=='stale':now+=timedelta(days=2)
    else:rows=rows[:4]
    current=statistics.assess_current_predictive_skill(policy,rows,now=now)
    gate='prospective_freshness' if damage=='stale' else 'independent_days'
    assert current['recent_prospective']['24']['gates'][gate] is False
    assert current['statistical_forecast_gates_passed'] is False


def test_recent_monitor_is_independent_of_packet_order():
    policy,rows,now=assessment_inputs()
    before=statistics.assess_current_predictive_skill(policy,rows,now=now)
    after=statistics.assess_current_predictive_skill(policy,list(reversed(rows)),now=now)
    assert before==after
