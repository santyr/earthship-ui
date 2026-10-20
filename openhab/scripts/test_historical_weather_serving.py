from datetime import datetime,timedelta,timezone
from math import exp
from types import SimpleNamespace
import pytest


def test_historical_predictor_uses_causal_origin_bias_and_frozen_feature_contract(monkeypatch):
 from weather_learning.historical_serving import HistoricalPredictor
 import weather_learning.site_calibration as calibration
 from weather_learning.contracts import identity
 now=datetime(2026,10,20,2,tzinfo=timezone.utc);target=SimpleNamespace(target_at=now+timedelta(hours=6),mean_c=10.)
 calls=[]
 def predict(model,features,*,baseline,origin):calls.append((features,baseline,origin));return baseline+features['origin_bias_decay_c']
 monkeypatch.setattr(calibration,'predict',predict)
 model=dict(model_sha256='a'*64,trained_at=(now-timedelta(hours=1)).isoformat(),training_end=(now-timedelta(hours=2)).isoformat(),sample_count=1000)
 predictor=HistoricalPredictor(model,now=now,timezone_name='America/Denver',origin_bias_c=2.,sensor_epoch='epoch',target_dates=30)
 assert predictor.predict(target,sensor_epoch='epoch')['value_c']==pytest.approx(10.+2*exp(-.25))
 assert sorted(calls[0][0])==sorted(['google_c','lead_days','hour_sin','hour_cos','season_sin','season_cos','origin_bias_decay_c'])
 assert calls[0][2]==now
 with pytest.raises(ValueError,match='epoch'):predictor.predict(target,sensor_epoch='other')
