"""Numerical policy tests; no fitting, services or production evidence labels."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone

import pytest

from thermal_model import graduation_policy as policy

START=datetime(2026,6,1,12,tzinfo=timezone.utc)


def inputs():
    records=[]
    for day in range(35):
        issue=START+timedelta(days=day)
        for hours in (1,6,12,24):
            records.append(dict(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=hours)).isoformat(),
                horizon_hours=hours,regime='warm',persistence_error_f=(-1 if day%2 else 1)*2,
                recent_cycle_error_f=(-1 if day%2 else 1)*3))
    candidate=dict(artifact_sha256='a'*64,runtime_sha256='b'*64,
        trained_through='2026-07-15T00:00:00+00:00',created_at='2026-07-16T00:00:00+00:00',
        active_parameter_count=12,sensor_epochs={'air':'864142d5-99ee-4b7a-b5fc-e6a96e7274d8',
            'mass':'864142d5-99ee-4b7a-b5fc-e6a96e7274d8','outdoor':'864142d5-99ee-4b7a-b5fc-e6a96e7274d8'})
    intervals=dict(development_start='2026-06-01T00:00:00+00:00',development_end='2026-07-15T00:00:00+00:00',
        holdout_start='2026-07-18T00:00:00+00:00',holdout_end='2026-09-01T00:00:00+00:00',
        prospective_start='2026-07-18T00:00:00+00:00',prospective_end=None)
    return dict(development=records,declared_at='2026-07-17T00:00:00+00:00',
        intervals=intervals,candidate=candidate,regimes=['warm'])


def test_policy_declares_baseline_derived_caps_and_positive_skill_before_holdout():
    result=policy.derive_policy(**inputs())
    assert result['schema']=='earthship-thermal-graduation-policy/v1'
    assert result['thresholds']['1']['max_mae_f']==2
    assert result['thresholds']['24']['max_rmse_f']==2
    assert result['thresholds']['24']['max_mean_interval_width_f']==4
    assert result['thresholds']['24']['min_independent_windows']==35
    assert result['thresholds']['24']['min_independent_days']==35
    assert result['comparison_alpha']==pytest.approx(.05/32)
    assert result['required_skill_upper_bound_f']==0
    assert result['max_qualification_age_hours']==24
    assert result['release_qualification_claimed'] is False
    assert policy.validate_policy(result)==result


def test_dense_same_day_rows_cannot_replace_independent_development_days():
    values=inputs()
    for i,row in enumerate(values['development']):
        origin=START+timedelta(seconds=i)
        row['issue_at']=origin.isoformat();row['target_at']=(origin+timedelta(hours=row['horizon_hours'])).isoformat()
    with pytest.raises(ValueError,match='independent'):policy.derive_policy(**values)


@pytest.mark.parametrize('damage',['late_declaration','future_development','training_leak','epoch','boolean_parameter',
    'missing_horizon','unknown_regime','empty','nonfinite','active_override'])
def test_policy_refuses_ambiguous_or_leaking_preregistration(damage):
    values=inputs()
    if damage=='late_declaration':values['declared_at']='2026-07-19T00:00:00+00:00'
    elif damage=='future_development':values['development'][0]['target_at']='2026-07-20T12:00:00+00:00'
    elif damage=='training_leak':values['candidate']['trained_through']='2026-08-01T00:00:00+00:00'
    elif damage=='epoch':values['candidate']['sensor_epochs']['air']='unknown'
    elif damage=='boolean_parameter':values['candidate']['active_parameter_count']=True
    elif damage=='missing_horizon':values['development']=[r for r in values['development'] if r['horizon_hours']!=24]
    elif damage=='unknown_regime':values['regimes']=['winter']
    elif damage=='empty':values['development']=[]
    elif damage=='nonfinite':values['development'][0]['persistence_error_f']=float('nan')
    elif damage=='active_override':values['candidate']['active']=True
    with pytest.raises(ValueError):policy.derive_policy(**values)


@pytest.mark.parametrize('damage',['loss_tolerance','error_cap','support','threshold_date','candidate'])
def test_persisted_policy_cannot_weaken_its_derived_thresholds(damage):
    result=policy.derive_policy(**inputs())
    if damage=='loss_tolerance':result['required_skill_upper_bound_f']=1
    elif damage=='error_cap':result['thresholds']['24']['max_mae_f']=99
    elif damage=='support':result['thresholds']['24']['min_independent_windows']=1
    elif damage=='threshold_date':result['declared_at']='2026-07-19T00:00:00+00:00'
    elif damage=='candidate':result['candidate']['artifact_sha256']='c'*64
    with pytest.raises(ValueError):policy.validate_policy(result)
