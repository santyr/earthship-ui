from datetime import timedelta
from test_weather_site_response import START,rows


def test_unchanged_eligible_gain_evidence_reuses_original_training_clock():
 from weather_learning.training_cache import gain_if_changed
 data=rows();cutoff=START+timedelta(days=6);now=START+timedelta(days=11)
 model,fit=gain_if_changed(None,data,kind='wind_m_s',cutoff=cutoff,trained_at=now,prior_pairs=2)
 assert fit is True
 reused,fit=gain_if_changed(model,data,kind='wind_m_s',cutoff=cutoff,trained_at=now+timedelta(days=1),prior_pairs=2)
 assert fit is False and reused==model
 assert reused['trained_at']==now.isoformat()


def test_residual_cache_preserves_original_and_refits_changed_evidence():
 from weather_learning.training_cache import residual_if_changed
 from test_weather_site_calibration import rows as residual_rows
 data=residual_rows()
 # The existing fixture uses its own epoch; use that fixture's explicit clocks.
 from test_weather_site_calibration import T
 cutoff=T+timedelta(days=6);now=T+timedelta(days=20)
 model,fit=residual_if_changed(None,data,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=now,correction_limit=6.)
 other,fit=residual_if_changed(model,data,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=now+timedelta(days=1),correction_limit=6.)
 assert fit is False and other==model
 fresh,fit=residual_if_changed(model,data,kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=now+timedelta(days=1),correction_limit=6.)
 assert fit is True and fresh['sample_count']>model['sample_count']
