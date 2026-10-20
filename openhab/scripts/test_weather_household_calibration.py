from datetime import timedelta
import pytest
from test_household_pv_window import START


def hours():
 result=[]
 for day in range(30):
  for hour in range(24):
   start=START+timedelta(days=day,hours=hour)
   result.append(dict(start=start.isoformat(),end=(start+timedelta(hours=1)).isoformat(),ac_w=100+(hour%6)*10+(day%3)*5,
       dc_kwh=.36,soc_change=2.,pv_input_kwh=.5,pv_output_kwh=.48,source_sha256='a'*64))
 return result


def test_household_capacity_and_conversion_are_separate_and_chronological():
 from weather_learning.household_calibration import fit_storage,assess_storage,fit_conversion
 rows=hours();cutoff=START+timedelta(days=24);now=START+timedelta(days=31)
 storage=fit_storage(rows,cutoff=cutoff,trained_at=now,nominal_kwh=20.48)
 assert storage['apparent_capacity_kwh']==pytest.approx(18)
 report=assess_storage(storage,rows,start=cutoff,end=START+timedelta(days=30))
 assert report['candidate_soc_change_mae']<1e-8
 assert report['baseline_soc_change_mae']>0
 conversion=fit_conversion(rows,cutoff=cutoff,trained_at=now)
 assert conversion['input_to_output_gain']==pytest.approx(.96)
 assert conversion['target']=='controller_output_given_measured_controller_input'
 assert conversion['forecasts_battery_acceptance'] is False
 changed=[dict(r,dc_kwh=100) if r['end']>cutoff.isoformat() else r for r in rows]
 assert fit_storage(changed,cutoff=cutoff,trained_at=now,nominal_kwh=20.48)==storage


def test_load_comparison_uses_only_completed_history_and_keeps_persistence():
 from weather_learning.household_calibration import fit_load_adjustment,assess_load_adjustment,predict_load
 rows=hours();cutoff=START+timedelta(days=24);now=START+timedelta(days=31)
 model=fit_load_adjustment(rows,cutoff=cutoff,trained_at=now)
 report=assess_load_adjustment(model,rows,start=cutoff,end=START+timedelta(days=30))
 assert report['pairs']>0
 assert set(report['mae_w'])=={'daily_profile','current_load_persistence','hourly_adjusted_profile'}
 assert report['prospective_score'] is False
 changed=[dict(r,ac_w=9999) if r['end']>cutoff.isoformat() else r for r in rows]
 assert fit_load_adjustment(changed,cutoff=cutoff,trained_at=now)==model
 with pytest.raises(ValueError,match='available'):predict_load(model,rows,origin=cutoff,lead_hours=1)


def test_daily_load_baseline_is_frozen_at_completed_local_midnight():
 from datetime import datetime,timezone
 from zoneinfo import ZoneInfo
 from weather_learning.household_calibration import _load_context
 from household_ac_load_model import fit_profile
 zone=ZoneInfo('America/Denver');origin=datetime(2026,10,20,18,tzinfo=timezone.utc)
 cutoff=origin.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
 floor=(cutoff.astimezone(zone)-timedelta(days=14)).astimezone(timezone.utc)
 rows=[];at=floor
 while at<origin:
  watts=100 if (at-floor).days<7 or at>=cutoff else 300
  rows.append(dict(start=at.isoformat(),end=(at+timedelta(hours=1)).isoformat(),ac_w=watts))
  at+=timedelta(hours=1)
 changed=[dict(r,ac_w=9999) if r['start']>=cutoff.isoformat() else r for r in rows]
 baseline,residual,persistence=_load_context(rows,origin)
 updated,new_residual,new_persistence=_load_context(changed,origin)
 assert updated==baseline
 assert new_residual!=residual and new_persistence==9999 and new_persistence!=persistence
 qualified=[dict(start=r['start'],end=r['end'],known_ac_kwh=r['ac_w']/1000,covered_seconds=3600) for r in rows if r['end']<=cutoff.isoformat()]
 deployed=fit_profile(hourly_rows=qualified,training_end=cutoff,trained_at=origin)
 assert baseline==pytest.approx({int(hour):value['median_ac_w'] for hour,value in deployed['hours'].items()})


def test_repeated_dst_hour_does_not_count_as_an_independent_training_day():
 from datetime import datetime,timezone
 from zoneinfo import ZoneInfo
 from weather_learning.household_calibration import _load_context
 zone=ZoneInfo('America/Denver');origin=datetime(2026,11,2,18,tzinfo=timezone.utc)
 # Nov 1 contains two local 01:00 hours; only two independent dates exist.
 starts=[datetime(2026,10,31,7,tzinfo=timezone.utc),datetime(2026,11,1,7,tzinfo=timezone.utc),datetime(2026,11,1,8,tzinfo=timezone.utc)]
 rows=[dict(start=at.isoformat(),end=(at+timedelta(hours=1)).isoformat(),ac_w=100) for at in starts]
 assert all(at.astimezone(zone).hour==1 for at in starts)
 assert _load_context(rows,origin)[0][1] is None
