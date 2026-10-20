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
 features=dict(google_c=10.,lead_days=.25,hour_sin=0.,hour_cos=1.,season_sin=0.,season_cos=1.,origin_bias_decay_c=1.)
 row=dict(schema='earthship-historical-learning-pair/v1',kind='outdoor_temperature_c',origin=(now-timedelta(days=1)).isoformat(),
  target_at=(now-timedelta(hours=2)).isoformat(),lead_hours=22,availability_basis='synthetic_original',forecast_sha256='a'*64,
  features=features,baseline=10.,outcome=12.,label={},origin_labels=[],prospective_score=False,automatic_actuation=False)
 row['pair_sha256']=identity(row)
 model=calibration.fit_residual([row],kind='outdoor_temperature_c',cutoff=now-timedelta(hours=1),
  trained_at=now-timedelta(hours=1),correction_limit=6.)
 predictor=HistoricalPredictor(model,now=now,timezone_name='America/Denver',origin_bias_c=2.,sensor_epoch='epoch',target_dates=30)
 assert predictor.predict(target,sensor_epoch='epoch')['value_c']==pytest.approx(10.+2*exp(-.25))
 assert sorted(calls[0][0])==sorted(['google_c','lead_days','hour_sin','hour_cos','season_sin','season_cos','origin_bias_decay_c'])
 assert calls[0][2]==now
 with pytest.raises(ValueError,match='epoch'):predictor.predict(target,sensor_epoch='other')
