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
