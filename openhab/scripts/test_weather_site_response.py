from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from weather_learning.contracts import identity
START=datetime(2026,10,1,tzinfo=timezone.utc)


def rows():
 values=[]
 for day in range(10):
  origin=START+timedelta(days=day);target=origin+timedelta(hours=2)
  row=dict(kind='wind_m_s',origin=origin.isoformat(),target_start=(target-timedelta(hours=1)).isoformat(),target_end=target.isoformat(),baseline=4.,outcome=2.,source_sha256='a'*64,measurement_sha256='b'*64,measurement_quality='numeric_without_sensor_health',prospective_score=False,automatic_actuation=False,availability_basis='retrospective_assumed_full_cycle_9h')
  row['pair_sha256']=identity(row);values.append(row)
 return values


def test_response_fit_uses_only_earlier_targets_and_later_issues():
 from weather_learning.weather_response import fit_gain,evaluate_gain,predict_gain
 data=rows();cutoff=START+timedelta(days=6);now=START+timedelta(days=11)
 model=fit_gain(data,kind='wind_m_s',cutoff=cutoff,trained_at=now,prior_pairs=2)
 assert model['gain']==pytest.approx(.625)
 result=evaluate_gain(model,data,start=cutoff,end=now)
 assert result['pairs']==4 and result['independent_target_days']==4
 assert result['candidate']['mae']<result['baseline']['mae']
 assert result['selected'] is True and result['prospective_score'] is False
 assert predict_gain(model,0,origin=now)==0
 with pytest.raises(ValueError,match='available'):predict_gain(model,4,origin=cutoff)
 changed=deepcopy(data)
 for row in changed[6:]:row['outcome']=100.;row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
 assert fit_gain(changed,kind='wind_m_s',cutoff=cutoff,trained_at=now,prior_pairs=2)==model


def test_wind_hour_requires_observed_coverage_and_never_fills_invalid_gaps():
 from weather_learning.weather_response import wind_hour
 data=[(START+timedelta(minutes=i),2.2369362921) for i in range(60)]
 value=wind_hour(data,start=START)
 assert value['mean_m_s']==pytest.approx(1.)
 assert value['covered_seconds']==3600
 assert value['measurement_health_qualified'] is False
 assert wind_hour([(START,2.2369362921),(START+timedelta(minutes=1),None)],start=START)['mean_m_s'] is None
