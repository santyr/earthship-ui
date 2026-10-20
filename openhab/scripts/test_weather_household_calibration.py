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
