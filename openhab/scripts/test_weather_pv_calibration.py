from datetime import timedelta
from copy import deepcopy
import pytest
from test_household_pv_window import START
from weather_learning.contracts import identity


def examples():
 rows=[]
 for day in range(12):
  at=START+timedelta(days=day)
  for hour in (1,2,3,4,5,6):
   row=dict(start=(at+timedelta(hours=hour)).isoformat(),end=(at+timedelta(hours=hour,minutes=5)).isoformat(),origin=at.isoformat(),
       baseline_w=400.+hour*100,outcome_w=(400.+hour*100)*1.2,azimuth_degrees=120+hour*20,lead_hours=hour,
       forecast_sha256='a'*64,energy_source_sha256=str(day%10)*64,potential_proxy_eligible=True)
   row['pair_sha256']=identity(row);rows.append(row)
 return rows


def test_pv_gain_uses_earlier_uncensored_proxy_labels_and_reports_later_errors():
 from weather_learning.pv_calibration import fit_gain,assess_gain,calibrated_power
 rows=examples();cutoff=START+timedelta(days=8);now=START+timedelta(days=20)
 model=fit_gain(rows,cutoff=cutoff,trained_at=now)
 report=assess_gain(model,rows,holdout_start=cutoff,holdout_end=START+timedelta(days=13))
 assert model['gain']==pytest.approx(1.2)
 assert report['candidate_mae_w']<1e-6
 assert report['baseline_mae_w']>100
 assert report['independent_target_days']==4
 assert report['selected'] is True
 assert report['physical_calibration_qualified'] is False
 assert calibrated_power(model,1000,origin=now)==pytest.approx(1200)
 assert calibrated_power(model,0,origin=now)==0
 with pytest.raises(ValueError,match='available'):calibrated_power(model,1000,origin=cutoff)
 changed=deepcopy(rows)
 for row in changed:
  if row['end']>=cutoff.isoformat():row['outcome_w']*=5;row.pop('pair_sha256');row['pair_sha256']=identity(row)
 assert fit_gain(changed,cutoff=cutoff,trained_at=now)==model


def test_pv_fit_cannot_use_censored_or_modified_labels():
 from weather_learning.pv_calibration import fit_gain
 rows=examples();rows[0]['outcome_w']+=1
 with pytest.raises(ValueError):fit_gain(rows,cutoff=START+timedelta(days=8),trained_at=START+timedelta(days=20))
 rows=examples()
 for row in rows:row['potential_proxy_eligible']=False;row.pop('pair_sha256');row['pair_sha256']=identity(row)
 with pytest.raises(ValueError,match='earlier'):fit_gain(rows,cutoff=START+timedelta(days=8),trained_at=START+timedelta(days=20))
