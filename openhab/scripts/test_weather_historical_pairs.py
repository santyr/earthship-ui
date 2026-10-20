from datetime import timedelta
import pytest
from weather_learning.tests.learning_fixtures import T,full_snapshot


def observations():
 result={}
 for hour in range(81):
  at=(T+timedelta(hours=hour)).isoformat()
  result[at]={name:dict(at=at,temperatureF=value,receiptVersion=1,sensorEpoch=None,sourceModel=model,sourceSensorId=sensor,
   snapshotSha256=str(hour%10)*64,receivedAt=at,storedAt=at,validUntil=(T+timedelta(hours=hour,seconds=120)).isoformat(),streamEpoch='00000000-0000-4000-8000-000000000001')
   for name,value,model,sensor in [('outdoor',50.,'Fineoffset-WH65B',206),('indoor',70.+hour*.01,'Fineoffset-WH32B',235),('north_wall',68.+hour*.01,'AmbientWeather-WH31E',193)]}
 return result


def pair(*,snapshot=None,measurements=None):
 from weather_learning.historical_pairs import pair_temperatures
 raw=snapshot or full_snapshot(hours=80);raw['historical']=True
 return pair_temperatures(raw,measurements or observations())


def test_pairs_historical_google_with_outdoor_air_and_mass_without_forged_epochs():
 rows=pair();kinds={r['kind'] for r in rows}
 assert kinds=={'outdoor_temperature_c','indoor_temperature_c','wall_temperature_c'}
 for row in rows:
  assert row['origin']==(T+timedelta(hours=9)).isoformat()
  assert row['target_at']>row['origin']
  assert row['availability_basis']=='retrospective_assumed_full_cycle_9h'
  assert row['label']['sensorEpoch'] is None
  assert row['label']['receiptVersion']==1
 air=next(r for r in rows if r['kind']=='indoor_temperature_c' and r['lead_hours']==3)
 assert air['baseline']==pytest.approx((70.09-32)*5/9)
 assert air['outcome']==pytest.approx((70.12-32)*5/9)
 assert air['features']['solar_kwh_m2']==pytest.approx(.3)


def test_missing_origin_or_forcing_cannot_become_a_thermal_training_example():
 raw=full_snapshot(hours=80)
 # Damage the original source consistently by using a station-only snapshot.
 from weather_learning.tests.learning_fixtures import native_snapshot
 rows=pair(snapshot=native_snapshot(hours=80))
 assert all(r['kind']=='outdoor_temperature_c' for r in rows)
 labels=observations();labels[(T+timedelta(hours=9)).isoformat()].pop('north_wall')
 rows=pair(measurements=labels)
 assert all(r['kind']=='outdoor_temperature_c' for r in rows)


def test_explicit_local_target_cutoff_excludes_future_labels():
 from weather_learning.historical_pairs import pair_temperatures
 raw=full_snapshot(hours=80);raw['historical']=True
 rows=pair_temperatures(raw,observations(),target_end=T+timedelta(hours=12))
 assert rows and all(r['target_at']<(T+timedelta(hours=12)).isoformat() for r in rows)


def test_historical_pairs_never_enter_prospective_feature_path():
 from weather_learning.features import temperature_targets
 raw=full_snapshot(hours=80);raw['historical']=True
 with pytest.raises(ValueError):temperature_targets(raw,issued_at=T+timedelta(hours=9))


def test_older_numeric_labels_keep_their_lower_quality_and_unknown_sensor_identity():
 from weather_learning.numeric_history import temperature_targets
 from thermal_model.schema import THERMAL_ITEMS
 labels=observations()
 for name,role in [('indoor','air'),('north_wall','mass'),('outdoor','outdoor')]:
  times=sorted(__import__('datetime').datetime.fromisoformat(at) for at in labels)
  events=[(at,labels[at.isoformat()][name]['temperatureF']) for at in times]
  values=temperature_targets(events,times,item=THERMAL_ITEMS[role],source_sha256='a'*64,unit='F')
  for at,value in zip(times,values):labels[at.isoformat()][name]=value
 rows=pair(measurements=labels)
 assert rows
 assert all(row['label']['provenance']=='persisted_numeric_state' for row in rows)
 assert all(row['label']['receiptVersion'] is None for row in rows)
 assert all(row['label']['receivedAt'] is None for row in rows)


def test_outdoor_correction_can_use_only_the_bias_observed_at_forecast_origin():
 from math import exp
 labels=observations();origin=(T+timedelta(hours=9)).isoformat();labels[origin]['outdoor']['temperatureF']=53.6
 first=pair(measurements=labels)
 target=(T+timedelta(hours=12)).isoformat()
 row=next(r for r in first if r['kind']=='outdoor_temperature_c' and r['target_at']==target)
 assert row['features']['origin_bias_decay_c']==pytest.approx(2*exp(-3/24))
 labels[target]['outdoor']['temperatureF']=80
 other=next(r for r in pair(measurements=labels) if r['kind']=='outdoor_temperature_c' and r['target_at']==target)
 assert other['features']==row['features']
 assert other['outcome']!=row['outcome']
