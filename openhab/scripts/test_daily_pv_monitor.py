from datetime import timedelta
from copy import deepcopy
import pytest
from test_household_pv_window import START,END
from test_weather_energy_history import source
from weather_learning.contracts import identity


def forecast():
 value=dict(schema='earthship-daily-pv-potential-receipt/v1',view=dict(schema='earthship-daily-pv-potential/v2',generatedAt=(START-timedelta(hours=1)).isoformat(),automatic_actuation=False,calibration={'modelSha256':'a'*64,'applyThroughAt':(START+timedelta(hours=23)).isoformat()}),
     calibration_source={'model':{'trained_at':(START-timedelta(days=1)).isoformat()}},projection_steps=[dict(start=(START+timedelta(minutes=5*i)).isoformat(),end=(START+timedelta(minutes=5*(i+1))).isoformat(),uncalibrated_w=1200.,potential_w=1000.,azimuth_degrees=110.,calibration_applied=True) for i in range(12)])
 value['receipt_sha256']=identity(value);return value


def test_prospective_pv_scoring_uses_actual_issue_and_qualified_input_intervals():
 from daily_pv_monitor import score_hour
 result=score_hour(forecast(),source(),assessed_at=END+timedelta(minutes=6))
 assert result['prospective_score'] is True
 assert result['eligible_bins']==12
 assert result['baseline_mae_w']==pytest.approx(200)
 assert result['candidate_mae_w']==pytest.approx(0)
 assert result['physical_calibration_qualified'] is False
 high=score_hour(forecast(),source(99),assessed_at=END+timedelta(minutes=6))
 assert high['status']=='awaiting_eligible_evidence'
 assert high['candidate_mae_w'] is None


def test_prospective_pv_score_rejects_post_origin_or_modified_forecasts():
 from daily_pv_monitor import score_hour
 original=forecast();original['view']['generatedAt']=(START+timedelta(minutes=1)).isoformat()
 original.pop('receipt_sha256');original['receipt_sha256']=identity(original)
 with pytest.raises(ValueError,match='before'):score_hour(original,source(),assessed_at=END+timedelta(minutes=6))
 original=forecast();original['projection_steps'][0]['potential_w']=999
 with pytest.raises(ValueError,match='identity'):score_hour(original,source(),assessed_at=END+timedelta(minutes=6))


def test_scoring_can_use_an_original_forecast_after_its_ui_display_expired(tmp_path):
 from daily_pv_monitor import choose_forecast,score_hour
 from weather_learning.contracts import canonical
 value=forecast();value['view']['validUntil']=(START+timedelta(minutes=30)).isoformat();value.pop('receipt_sha256');value['receipt_sha256']=identity(value)
 path=tmp_path/(value['receipt_sha256']+'.receipt.json');path.write_bytes(canonical(value));path.chmod(0o600)
 chosen=choose_forecast(tmp_path,START)
 assert chosen==value
 assert score_hour(chosen,source(),assessed_at=END+timedelta(minutes=6))['eligible_bins']==12
 assert choose_forecast(tmp_path,START-timedelta(hours=2)) is None
