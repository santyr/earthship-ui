"""The monitor scores only original constituent bins of confirmed daily views."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import pytest
from test_production_pv_worker import daily
from weather_learning.contracts import identity,canonical,instant
import test_weather_energy_history as history

def issued(daily):
 worker,args,_=daily;result=worker.run(**args,component_publish=True)
 receipt=json.loads((args['state_path']/(result['receipt_sha256']+'.receipt.json')).read_bytes())
 emission=json.loads((args['state_path']/(result['emission_sha256']+'.emission.json')).read_bytes())
 return dict(schema='earthship-confirmed-component-daily-forecast/v1',receipt=receipt,emission=emission)

def rehash(body,key):
 body[key]=identity({k:v for k,v in body.items() if k!=key})

def test_prepared_component_daily_is_never_selected_until_original_cache_is_confirmed(daily):
 from daily_pv_monitor import choose_forecast
 worker,args,_=daily;worker.run(**args)
 start=instant(history.source()['start'])
 assert choose_forecast(args['state_path'],start) is None
 original=issued(daily);chosen=choose_forecast(args['state_path'],start)
 assert chosen==original
 assert choose_forecast(args['state_path'],instant(original['emission']['published_at'])-timedelta(seconds=1)) is None

def test_confirmed_component_daily_scores_actual_original_native_bins_and_distinct_method(daily):
 from daily_pv_monitor import score_hour
 original=issued(daily);power=history.source()
 score=score_hour(original,power,assessed_at=instant(power['end'])+timedelta(minutes=6))
 assert score['schema']=='earthship-pv-prospective-hour-score/v4'
 assert score['eligible_bins']==12 and score['adjusted_bins']==12
 assert score['calibration_sha256']==original['receipt']['view']['calibration']['calibrationSha256']
 assert score['procedure_sha256']==original['receipt']['view']['calibration']['procedureSha256']
 assert score['forecast_emission_sha256']==original['emission']['emission_sha256']
 assert score['metric_population']=='constituent_five_minute_power_of_published_daily_totals'
 assert score['physical_calibration_qualified'] is False
 for pair in score['pairs']:assert pair['candidate_w']==pytest.approx(pair['baseline_w']*.8)

def test_component_score_accepts_the_original_fit_measurement_cohort(daily):
 from daily_pv_monitor import score_hour
 original=issued(daily);power=history.source()
 # The training producer names this field policy, not the raw-source field policy_raw.
 expected=identity(dict(policy=power['policy_raw'],bank_start=power['bank_start'],items=power['items']))
 assert original['receipt']['calibration_original']['context']['measurement_cohort_sha256']==expected
 score=score_hour(original,power,assessed_at=instant(power['end'])+timedelta(minutes=6))
 assert score['measurement_cohort_sha256']==expected
 assert score['eligible_bins']==12 and score['adjusted_bins']==12

@pytest.mark.parametrize('damage',['late_publication','wrong_view','changed_segment','wrong_cohort','changed_power_policy','changed_model'])
def test_component_scores_refuse_late_changed_or_cross_cohort_originals(daily,damage):
 from daily_pv_monitor import score_hour
 original=issued(daily);power=history.source();receipt=original['receipt'];emission=original['emission']
 if damage=='late_publication':emission['published_at']=(instant(power['start'])+timedelta(seconds=1)).isoformat();rehash(emission,'emission_sha256')
 elif damage=='wrong_view':emission['view_bytes_sha256']='f'*64;rehash(emission,'emission_sha256')
 elif damage=='wrong_cohort':power['items']['power']+=1;rehash(power,'source_sha256')
 elif damage=='changed_power_policy':power['policy_raw']+=' ';rehash(power,'source_sha256')
 elif damage=='changed_model':receipt['calibration_original']['model']['gain']=1.3;rehash(receipt,'receipt_sha256');emission['receipt_sha256']=receipt['receipt_sha256'];rehash(emission,'emission_sha256')
 else:
  receipt['component_windows'][0]['projection']['segments'][2]['potential_dc_w']+=1
  rehash(receipt,'receipt_sha256');emission['receipt_sha256']=receipt['receipt_sha256'];rehash(emission,'emission_sha256')
 with pytest.raises(ValueError):score_hour(original,power,assessed_at=instant(power['end'])+timedelta(minutes=6))

def test_component_report_separates_fitting_procedure_and_measurement_context_from_legacy(daily):
 from daily_pv_monitor import score_hour
 from daily_pv_performance import build_view
 original=issued(daily);power=history.source();now=instant(power['end'])+timedelta(minutes=6)
 score=score_hour(original,power,assessed_at=now)
 score.update(runtime_manifest={'daily_pv_monitor.py':'e'*64},original_file_sha256='f'*64);rehash(score,'score_sha256')
 view=build_view([score],generated_at=now);cohort=view['cohorts'][0]
 assert view['schema']=='earthship-pv-potential-performance/v2'
 assert cohort['procedure_sha256']==score['procedure_sha256']
 assert cohort['measurement_cohort_sha256']==score['measurement_cohort_sha256']
 assert cohort['baseline_rule']==score['baseline_rule']
 assert cohort['local_target_dates']==1 and 'independent_target_days' not in cohort

def test_raw_component_fallback_is_scored_without_borrowing_native_adjustment(daily,monkeypatch):
 from daily_pv_monitor import score_hour
 from test_production_pv import forecast
 import weather_learning.native_solar_forecast as native
 monkeypatch.setattr(native,'load_component_forecast',lambda *a,**k:forecast(hours=12,direct=None))
 original=issued(daily);power=history.source()
 score=score_hour(original,power,assessed_at=instant(power['end'])+timedelta(minutes=6))
 assert score['eligible_bins']==12 and score['adjusted_bins']==0
 assert score['candidate_mae_w']==score['baseline_mae_w']
 assert all(p['candidate_w']==p['baseline_w'] for p in score['pairs'])

def test_scoring_retains_original_fit_clocks_after_model_expiry_without_new_model_calls(daily,monkeypatch):
 from daily_pv_monitor import score_hour
 import weather_learning.production_pv as core
 original=issued(daily);power=history.source();before=canonical(original)
 monkeypatch.setattr(core,'load_calibration',lambda *a,**k:pytest.fail('scoring consulted current model'))
 score=score_hour(original,power,assessed_at=instant(power['end'])+timedelta(days=30))
 assert score['eligible_bins']==12 and canonical(original)==before

def test_component_and_legacy_report_cohorts_keep_distinct_population_and_date_fields(daily):
 from daily_pv_monitor import score_hour
 from daily_pv_performance import build_view
 original=issued(daily);power=history.source();now=instant(power['end'])+timedelta(minutes=6)
 score=score_hour(original,power,assessed_at=now)
 score.update(runtime_manifest={'daily_pv_monitor.py':'e'*64},original_file_sha256='f'*64);rehash(score,'score_sha256')
 legacy=deepcopy(score)
 for key in ('calibration_sha256','procedure_sha256','measurement_cohort_sha256','solar_grid_sha256','baseline_rule','forecast_emission_sha256','forecast_published_at','metric_population','target_timezone'):legacy.pop(key)
 legacy['schema']='earthship-pv-prospective-hour-score/v3';rehash(legacy,'score_sha256')
 view=build_view([score,legacy],generated_at=now)
 assert len(view['cohorts'])==2 and view['scored_hours']==1
 old=next(c for c in view['cohorts'] if c['metric_population']=='legacy_original_five_minute_power')
 assert old['procedure_sha256'] is None and old['measurement_cohort_sha256'] is None and old['baseline_rule'] is None
 assert old['local_target_dates']==1
