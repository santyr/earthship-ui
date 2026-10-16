"""Synthetic chronological AC-load learning; production history is never fitted here."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from copy import deepcopy
import importlib
import pytest
from household.codec import identity

ZONE=ZoneInfo('America/Denver')
END=datetime(2026,10,4,tzinfo=ZONE).astimezone(timezone.utc)


def hours(days=3,*,coverage=1.,first=None):
    first=first or END-timedelta(days=days);out=[]
    for i in range(days*24):
        at=first+timedelta(hours=i);watts=100+(i//24)*100+at.astimezone(ZONE).hour*10
        out.append(dict(start=at.isoformat(),end=(at+timedelta(hours=1)).isoformat(),known_ac_kwh=watts*coverage/1000,covered_seconds=3600*coverage))
    return out


def learn(rows=None,**overrides):
    api=importlib.import_module('household_ac_load_model')
    args=dict(hourly_rows=hours() if rows is None else rows,training_end=END,trained_at=END+timedelta(hours=1),timezone_name='America/Denver')
    args.update(overrides);return api,api.fit_profile(**args)


def test_hourly_profile_uses_independent_days_and_preserves_training_lineage():
    api,model=learn();row=model['hours']['10']
    assert model['status']=='profiled' and row['origin_days']==3
    assert row['median_ac_w']==300 and row['training_min_ac_w']==200 and row['training_max_ac_w']==400
    assert model['inputs']['hourly_rows']==hours() and model['model_sha256']==identity({k:v for k,v in model.items() if k!='model_sha256'})
    assert api.replay_profile(model)==model and model['automatic_actuation'] is False


def test_forecast_integrates_clock_hour_profile_over_original_elapsed_hour():
    api,model=learn();issue=END+timedelta(hours=10,minutes=30)
    forecast=api.project_load(model,origin=issue,now=issue+timedelta(seconds=1))
    # Local hours10/11 have median300/310W: half each in the first elapsed hour.
    assert forecast['status']=='projected' and len(forecast['trajectory'])==24
    assert forecast['trajectory'][0]['mean_ac_w']==305 and forecast['trajectory'][0]['ac_kwh']==pytest.approx(.305)
    assert forecast['trajectory'][0]['at']==(issue+timedelta(hours=1)).isoformat()
    assert forecast['trained_through']==END.isoformat() and forecast['model_sha256']==model['model_sha256']
    assert forecast['prediction_intervals'] is None and forecast['physical_calibration_qualified'] is False


def test_missing_intervals_are_not_zero_load_and_insufficient_hour_support_is_explicit():
    rows=hours(coverage=.995);api,model=learn(rows)
    assert model['hours']['10']['median_ac_w']==pytest.approx(300)
    assert model['hours']['10']['observed_seconds']==pytest.approx(3*3600*.995)
    for row in rows:
        if datetime.fromisoformat(row['start']).astimezone(ZONE).hour==10:row['covered_seconds']=1800;row['known_ac_kwh']=.15
    _,model=learn(rows);assert model['status']=='insufficient_support' and model['hours']['10']['median_ac_w'] is None
    issue=END+timedelta(hours=2)
    assert api.project_load(model,origin=issue,now=issue)['status']=='unavailable'


@pytest.mark.parametrize('damage',['future','overlap','duplicate','unknown_field','energy_without_coverage','bad_energy','bad_cutoff','train_before_cutoff'])
def test_invalid_or_lookahead_training_data_refuses(damage):
    rows=hours();extra={}
    if damage=='future':rows[-1]['end']=(END+timedelta(hours=1)).isoformat()
    elif damage in ('duplicate','overlap'):rows[1]=deepcopy(rows[0])
    elif damage=='unknown_field':rows[0]['scalar_load_guess']=100
    elif damage=='energy_without_coverage':rows[0]['covered_seconds']=0
    elif damage=='bad_energy':rows[0]['known_ac_kwh']=-1
    elif damage=='bad_cutoff':extra['training_end']=END+timedelta(hours=1)
    else:extra['trained_at']=END-timedelta(seconds=1)
    with pytest.raises(ValueError):learn(rows,**extra)


def test_resealed_changed_coefficients_refuse_original_training_replay():
    api,model=learn();model['hours']['10']['median_ac_w']=1
    model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
    with pytest.raises(ValueError):api.replay_profile(model)


def test_model_expiry_uses_original_training_cutoff_not_cache_read_time():
    api,model=learn();issue=END+timedelta(hours=36)
    result=api.project_load(model,origin=issue,now=issue)
    assert result['status']=='unavailable' and result['reason']=='load_model_expired' and result['trajectory']==[]


def test_dst_fall_fold_is_one_independent_day_and_future_horizon_is_elapsed_24h():
    end=datetime(2026,11,2,tzinfo=ZONE).astimezone(timezone.utc);start=datetime(2026,10,30,tzinfo=ZONE).astimezone(timezone.utc)
    rows=[];at=start
    while at<end:
        rows.append(dict(start=at.isoformat(),end=(at+timedelta(hours=1)).isoformat(),known_ac_kwh=.3,covered_seconds=3600.));at+=timedelta(hours=1)
    api,model=learn(rows,training_end=end,trained_at=end+timedelta(hours=1))
    assert model['hours']['1']['origin_days']==3 and model['hours']['1']['observed_seconds']==4*3600
    issue=end+timedelta(hours=2);forecast=api.project_load(model,origin=issue,now=issue)
    assert len(forecast['trajectory'])==24 and datetime.fromisoformat(forecast['trajectory'][-1]['at'])-issue==timedelta(hours=24)
    assert forecast['total_ac_kwh']==pytest.approx(7.2)


@pytest.mark.parametrize('month,day,expected_last_hour',[(3,8,1),(11,1,23)])
def test_forecast_across_DST_keeps_exact_elapsed_targets(month,day,expected_last_hour):
    local_issue=datetime(2026,month,day,0,30,tzinfo=ZONE);issue=local_issue.astimezone(timezone.utc)
    end=(local_issue-timedelta(days=1)).replace(hour=0,minute=0).astimezone(timezone.utc)
    rows=hours(first=end-timedelta(days=3))
    api,model=learn(rows,training_end=end,trained_at=end+timedelta(hours=1))
    forecast=api.project_load(model,origin=issue,now=issue)
    last=datetime.fromisoformat(forecast['trajectory'][-1]['at'])
    assert last-issue==timedelta(hours=24) and last.astimezone(ZONE).hour==expected_last_hour


def test_a_new_cutoff_cannot_refresh_old_training_observations():
    last=END-timedelta(days=2);rows=hours(first=last-timedelta(days=3))
    api,model=learn(rows);issue=END+timedelta(hours=2)
    result=api.project_load(model,origin=issue,now=issue)
    assert result['trained_through']==last.isoformat() and result['training_cutoff']==END.isoformat()
    assert result['status']=='unavailable' and result['reason']=='load_model_expired'
