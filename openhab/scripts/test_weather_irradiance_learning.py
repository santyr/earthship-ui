from datetime import timedelta
from test_household_pv_window import START
import pytest


def test_legacy_proxy_hour_uses_only_observed_time_and_preserves_invalid_barriers():
 from weather_learning.irradiance_learning import numeric_hour
 complete=[(START+timedelta(minutes=i),600.) for i in range(60)]
 result=numeric_hour(complete,start=START)
 assert result['mean_w_m2']==pytest.approx(600)
 assert result['covered_seconds']==3600
 sparse=[(START,600.),(START+timedelta(seconds=180),None)]
 result=numeric_hour(sparse,start=START)
 assert result['mean_w_m2'] is None
 assert result['covered_seconds']==120
 assert numeric_hour(complete+[(START+timedelta(hours=1),1200.)],start=START)==numeric_hour(complete,start=START)


def test_radiation_hour_never_promotes_a_partial_receipt_window_to_a_training_label():
 from weather_learning.irradiance_learning import qualified_hour
 from weather_radiation_evidence import RadiationPolicy
 result=qualified_hour([],start=START,history_start=START-timedelta(seconds=120),cutover=START,policy=RadiationPolicy(sensor_id=1),assessed_at=START+timedelta(hours=2))
 assert result['mean_w_m2'] is None
 assert result['quality']=='native_receipts_unqualified'


def test_irradiance_pairing_uses_ending_hour_target_and_native_midpoint(monkeypatch):
 from weather_learning.irradiance_learning import pair_irradiance
 from weather_learning.contracts import identity
 import weather_learning.historical as history
 init=START.replace(hour=0,minute=0);origin=init+timedelta(hours=9);end=origin+timedelta(hours=1);mid=end-timedelta(minutes=30)
 source=dict(historical=True,initialized_at=init.isoformat(),points=[dict(variable='surface_solar_radiation_downwards_1hr',statistic='mean',valid_at=end.isoformat(),value=500.)])
 monkeypatch.setattr(history,'verify_history',lambda x:x)
 labels={end.isoformat():dict(mean_w_m2=400.,source_sha256='a'*64,quality='clean_v2_elapsed_lux_proxy',measurement_health_qualified=True)}
 positions={mid.isoformat():dict(elevation_degrees=30.,azimuth_degrees=165.,horizon_elevation_degrees=15.)}
 rows=pair_irradiance(source,labels,positions,target_end=end+timedelta(hours=1))
 assert len(rows)==1
 row=rows[0]
 assert row['baseline']==500 and row['outcome']==400
 assert row['lead_hours']==1
 assert row['features']['horizon_margin_degrees']==15
 assert row['label']['source_sha256']=='a'*64
 assert row['forecast_sha256']==identity(source)
 labels[end.isoformat()]['mean_w_m2']=None
 assert pair_irradiance(source,labels,positions,target_end=end+timedelta(hours=1))==[]


def test_irradiance_assessment_reports_recent_receipt_subset_and_clamps_zero(monkeypatch):
 from weather_learning.irradiance_learning import assess_irradiance
 import weather_learning.site_calibration as calibration
 from weather_learning.contracts import identity
 cutoff=START+timedelta(days=1);rows=[]
 for i,quality in enumerate(('clean_v2_elapsed_lux_proxy','legacy_numeric_without_sensor_receipts')):
  row=dict(schema='earthship-historical-learning-pair/v1',kind='irradiance_w_m2',origin=cutoff.isoformat(),target_at=(cutoff+timedelta(hours=i+1)).isoformat(),lead_hours=i+1,
   availability_basis='retrospective_assumed_full_cycle_9h',forecast_sha256='a'*64,features={'elevation_degrees':10.,'azimuth_degrees':165.},baseline=10.,outcome=0.,label={'quality':quality},origin_labels={},prospective_score=False,automatic_actuation=False)
  row['pair_sha256']=identity(row);rows.append(row)
 monkeypatch.setattr(calibration,'_model',lambda x:x);monkeypatch.setattr(calibration,'_calculate',lambda *a:-20.)
 report=assess_irradiance({'kind':'irradiance_w_m2','model_sha256':'b'*64,'cutoff':cutoff.isoformat()},rows,holdout_start=cutoff,holdout_end=cutoff+timedelta(days=1))
 assert report['pairs']==2
 assert report['candidate']['mae']==0
 assert report['by_quality']['clean_v2_elapsed_lux_proxy']['pairs']==1
 assert report['by_lead']['0-24h']['pairs']==2
 assert report['baseline_target']=='raw_google_ending_hour_ghi_against_lux_proxy'


def test_legacy_radiation_units_require_consistent_multiday_receipt_overlap():
 from weather_learning.irradiance_learning import infer_proxy_units
 overlaps=[dict(date='2026-10-'+str(day),pairs=[(400.,402.),(600.,603.),(500.,499.)],numeric_sha256='a'*64,radiation_sha256='b'*64) for day in (16,17,18)]
 proof=infer_proxy_units(overlaps)
 assert proof['unit']=='W_m2_lux_proxy'
 assert len(proof['overlap_days'])==3
 assert proof['hardware_health_assumed_before_receipts'] is False
 with pytest.raises(ValueError,match='consistent'):
  infer_proxy_units(overlaps[:2])
 overlaps[-1]['pairs']=[(400.*126.7,400.),(600.*126.7,600.),(500.*126.7,500.)]
 with pytest.raises(ValueError,match='consistent'):infer_proxy_units(overlaps)


def test_thermal_irradiance_replay_preserves_originals_night_and_training_latency(monkeypatch):
 from weather_learning.irradiance_learning import correct_forcing_hours
 from weather_learning import site_calibration
 import copy
 origin=START.replace(minute=0,second=0,microsecond=0);end=origin+timedelta(hours=1);mid=end-timedelta(minutes=30)
 hours={origin.isoformat():{'station_head_temperature_2m':10.,'surface_solar_radiation_downwards_1hr':0.},end.isoformat():{'station_head_temperature_2m':11.,'surface_solar_radiation_downwards_1hr':500.}}
 original=copy.deepcopy(hours);positions={mid.isoformat():{'elevation_degrees':30.,'azimuth_degrees':165.}}
 monkeypatch.setattr(site_calibration,'_model',lambda x:x);monkeypatch.setattr(site_calibration,'_calculate',lambda *a:300.)
 model={'cutoff':(origin-timedelta(hours=1)).isoformat(),'kind':'irradiance_w_m2'}
 result=correct_forcing_hours(hours,model=model,origin=origin,positions=positions,horizon_profile=[{'azimuth_degrees':i*7.5,'elevation_degrees':0.} for i in range(48)],horizon_hours=1)
 assert result[end.isoformat()]['surface_solar_radiation_downwards_1hr']==300
 assert result[end.isoformat()]['station_head_temperature_2m']==11
 assert hours==original
 positions[mid.isoformat()]['elevation_degrees']=-5
 assert correct_forcing_hours(hours,model=model,origin=origin,positions=positions,horizon_profile=None,horizon_hours=1)==original
 model['cutoff']=origin.isoformat()
 with pytest.raises(ValueError,match='ready'):correct_forcing_hours(hours,model=model,origin=origin,positions=positions,horizon_profile=None,horizon_hours=1)
