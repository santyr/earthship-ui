from datetime import timedelta
from copy import deepcopy
import pytest
from test_household_pv_window import START
from weather_learning.contracts import identity


def rows():
 result=[]
 for day in range(12):
  for i in range(16):
   at=START+timedelta(days=day,minutes=5*(i+1));east=i<8
   row=dict(start=at.isoformat(),end=(at+timedelta(minutes=5)).isoformat(),origin=START.isoformat(),baseline_w=1000.,outcome_w=700. if east else 1300.,azimuth_degrees=110. if east else 240.,lead_hours=2.,forecast_sha256='a'*64,energy_source_sha256='b'*64,potential_proxy_eligible=True)
   row['pair_sha256']=identity(row);result.append(row)
 return result


def test_directional_gain_preserves_unsupported_directions_and_improves_opposite_biases():
 from weather_learning.pv_directional_calibration import fit_directional,assess_directional,project_power
 data=rows();cutoff=START+timedelta(days=8);now=START+timedelta(days=20)
 model=fit_directional(data,cutoff=cutoff,trained_at=now)
 assert project_power(model,1000,azimuth_degrees=110,origin=now)<1000
 assert project_power(model,1000,azimuth_degrees=240,origin=now)>1000
 assert project_power(model,1000,azimuth_degrees=175,origin=now)==1000
 assert project_power(model,0,azimuth_degrees=110,origin=now)==0
 # Reuse actual later origin clocks in the synthetic holdout.
 for r in data:
  if r['start']>=cutoff.isoformat():r['origin']=(__import__('datetime').datetime.fromisoformat(r['start'])-timedelta(hours=1)).isoformat();r.pop('pair_sha256');r['pair_sha256']=identity(r)
 report=assess_directional(model,data,holdout_start=cutoff,holdout_end=START+timedelta(days=13))
 assert report['selected'] is True
 assert report['candidate_mae_w']<report['baseline_mae_w']
 changed=deepcopy(data)
 for r in changed:
  if r['end']>=cutoff.isoformat():r['outcome_w']=20000.;r.pop('pair_sha256');r['pair_sha256']=identity(r)
 assert fit_directional(changed,cutoff=cutoff,trained_at=now)==model
 with pytest.raises(ValueError,match='available'):project_power(model,1000,azimuth_degrees=110,origin=cutoff)
