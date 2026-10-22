"""Matched rain comparisons preserve causal coverage and wet-event limits."""
from datetime import datetime,timedelta,timezone
from importlib import import_module
import pytest
from test_rain_calibration import POLICY,PRODUCTS,rain_snapshot
from test_rain_two_part import balanced
from weather_learning.rain_calibration import make_forecast,make_observation
from weather_learning.contracts import instant
from test_weather_rain_day import POLICY as NATIVE


def api():return import_module('weather_learning.rain_evaluation')


def report(data,**kwargs):return api().evaluate_rain(*data,assessed_at=datetime(2026,6,16,tzinfo=timezone.utc),policy=POLICY,**kwargs)


def test_all_three_heads_share_exact_targets_and_report_wet_amount_and_uncertainty(balanced):
 result=report(balanced);assert result['matched_targets']==12
 assert len(result['cohorts'])==1;cohort=next(iter(result['cohorts'].values()))
 assert cohort['raw'][PRODUCTS[0]]['point']['mae_mm']==pytest.approx(1.488)
 assert cohort['raw'][PRODUCTS[1]]['point']['mae_mm']==pytest.approx(4.5)
 assert cohort['raw'][PRODUCTS[2]]['point']['mae_mm']==pytest.approx(7.512)
 assert cohort['raw'][PRODUCTS[0]]['wet_amount']['mae_mm']==pytest.approx(2.952)
 assert cohort['raw'][PRODUCTS[0]]['event']['hits']==6
 assert cohort['raw'][PRODUCTS[0]]['event']['false_alarms']==cohort['raw'][PRODUCTS[0]]['event']['misses']==0
 assert cohort['raw'][PRODUCTS[0]]['event']['probability_claim'] is False
 assert cohort['disposition']=='insufficient_evidence' and cohort['selected'] is False
 assert cohort['outer']['independent_dates']==4
 assert cohort['timing']['status']=='insufficient_evidence'
 assert result['raw_production_rain_retained'] is True and result['automatic_actuation'] is False


def test_incomplete_latest_head_removes_the_whole_target_from_product_comparison(balanced):
 fore,out=balanced;source,start,end=rain_snapshot(datetime(2026,6,1).date(),'UTC',mean_mm=.25,missing=PRODUCTS[1]);issue=start-timedelta(hours=2)
 later=make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 result=report(([later,*fore],out));assert result['matched_targets']==11
 cohort=next(iter(result['cohorts'].values()));assert {s['point']['targets'] for s in cohort['raw'].values()}=={11}
 assert result['withheld']['missing_precipitation_head']==1


def test_missing_resolution_keeps_continuous_depth_without_fabricated_event_scores(balanced):
 fore,out=balanced;unmeasured=[]
 for original in out:
  value=original.to_dict();r=value['request']
  unmeasured.append(make_observation(start=instant(r['start']),end=instant(r['end']),requested_at=instant(r['requested_at']),received_at=instant(r['received_at']),cutover=instant(r['cutover']),observations=[(instant(at),raw) for at,raw in value['sources']['observations']],policy=NATIVE,resolution_source=None,experiment_policy=POLICY))
 result=report((fore,unmeasured));cohort=next(iter(result['cohorts'].values()))
 assert cohort['raw'][PRODUCTS[0]]['point']['mae_mm']==pytest.approx(1.488)
 assert cohort['raw'][PRODUCTS[0]]['event']['classified_targets']==0
 assert cohort['candidate']['occurrence']['brier'] is None
 assert cohort['candidate']['coverage']['predicted_targets']==0
 assert cohort['candidate']['fallback_policy']['point']==cohort['raw'][PRODUCTS[0]]['point']
 assert cohort['disposition']=='insufficient_evidence'


def test_probability_reliability_and_day_block_pairing_have_analytic_values():
 module=api();result=module.occurrence_metrics([.8,.2,.6,.4],[1,0,0,1])
 assert result['brier']==pytest.approx(.2)
 assert result['event']['hits']==result['event']['false_alarms']==result['event']['misses']==1
 assert result['reliability'][8]['count']==1 and result['reliability'][8]['observed_frequency']==1
 bootstrap=module.paired_bootstrap([dict(date='2026-06-01',candidate=1.,baseline=2.),dict(date='2026-06-02',candidate=1.,baseline=2.)],policy=POLICY)
 assert bootstrap['mean_difference']==bootstrap['lower_95']==bootstrap['upper_95']==-1.
 assert bootstrap['blocks']==2 and bootstrap['resamples']==500


def test_dry_only_gain_cannot_pass_selection_even_with_perfect_aggregate_scores():
 decision=api().selection_decision(dict(independent_dates=12,wet_targets=0,below_threshold_targets=12,wet_events=0),amount_improvement=.5,brier_improvement=.5,amount_interval=[-.5,-.1],brier_interval=[-.5,-.1],subgroups=[],policy=POLICY)
 assert decision['disposition']=='insufficient_evidence' and decision['selected'] is False


def test_candidate_cannot_win_by_improving_dry_days_while_wet_amount_worsens():
 module=api();counts=dict(independent_dates=12,wet_targets=6,below_threshold_targets=6,wet_events=3)
 rejected=module.selection_decision(counts,amount_improvement=.5,brier_improvement=.5,amount_interval=[-.5,-.1],brier_interval=[-.5,-.1],wet_amount_improvement=-.01,wet_amount_interval=[.01,.02],subgroups=[],policy=POLICY)
 assert rejected['eligible_for_review'] is False and rejected['selected'] is False
 assert rejected['reason']=='wet_amount_improvement_not_demonstrated'
 accepted=module.selection_decision(counts,amount_improvement=.5,brier_improvement=.5,amount_interval=[-.5,-.1],brier_interval=[-.5,-.1],wet_amount_improvement=.2,wet_amount_interval=[-.3,-.1],subgroups=[],policy=POLICY)
 assert accepted['eligible_for_review'] is True and accepted['selected'] is False


def test_hourly_timing_requires_complete_qualified_brackets_and_does_not_invent_a_peak():
 from test_weather_rain_day import snapshot as packet
 from weather_learning.rain_calibration import make_observation
 source,start,end=rain_snapshot(datetime(2026,6,1).date(),'UTC',mean_mm=.25);issue=start-timedelta(hours=3)
 forecast=make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 at=start-timedelta(seconds=30);rows=[]
 while at<=end+timedelta(seconds=120):
  rows.append(packet(at,len(rows)+1,10.+(.12 if at>=start+timedelta(hours=12,minutes=30) else 0.)));at+=timedelta(seconds=90)
 observations=[]
 for h in range(24):
  left=start+timedelta(hours=h);right=left+timedelta(hours=1);before=[r for r in rows if r[0]<left]
  observations.append(make_observation(start=left,end=right,requested_at=end+timedelta(seconds=120),received_at=end+timedelta(seconds=121),cutover=start-timedelta(days=1),observations=before[-1:]+[r for r in rows if left<=r[0]<=right+timedelta(seconds=120)],policy=NATIVE,resolution_source=None,experiment_policy=POLICY))
 result=api().score_hourly_timing(forecast,observations,assessed_at=end+timedelta(days=1),policy=POLICY)
 assert result['status']=='available' and result['matched_hours']==24
 assert result['heads'][PRODUCTS[0]]['depth_weighted_centroid_error_hours']==pytest.approx(.5)
 assert result['heads'][PRODUCTS[0]]['peak_hour_absolute_error_hours'] is None
 assert result['heads'][PRODUCTS[0]]['peak_reason']=='nonunique_native_peak'
 missing=api().score_hourly_timing(forecast,observations[:-1],assessed_at=end+timedelta(days=1),policy=POLICY)
 assert missing['status']=='insufficient_evidence' and missing['heads']=={}


def test_zero_error_baseline_is_known_without_dividing_by_zero():
 assert api()._improvement(0.,0.)==0.
 assert api()._improvement(1.,0.) is None


def test_evaluation_does_not_consume_predictions_prepared_after_its_assessment(balanced):
 from test_rain_two_part import fit,future
 from weather_learning.rain_issues import make_issue
 model=fit(balanced)['model'];issue=make_issue(future(.25),model=model,observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY,prepared_at=datetime(2026,6,17,tzinfo=timezone.utc),mode='causal_retrospective_experiment')
 result=report(balanced,issues=[issue])
 assert result['withheld']['prediction_prepared_after_assessment']==1


def test_experiment_and_prospective_issue_populations_are_not_pooled(balanced):
 from test_rain_two_part import future
 from weather_learning.rain_issues import make_issue
 f=future(.25);issue=make_issue(f,model=None,observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY,prepared_at=instant(f.to_dict()['completed_at']),mode='prospective_shadow')
 result=report(balanced,issues=[issue]);assert result['withheld']['different_prediction_mode']==1
 assert result['prediction_mode']=='causal_retrospective_experiment'


def test_full_outer_candidate_experiment_is_causal_bounded_and_remains_unselected():
 from test_rain_two_part import population
 from weather_learning.rain_two_part import fit_two_part
 from weather_learning.rain_issues import make_issue
 forecasts,observations=population(days=36);issues=[];prepared=datetime(2026,7,8,tzinfo=timezone.utc);cohort=observations[0].to_dict()['cohort_sha256']
 # Exactly the final third is assessed. Each deterministic fit uses only
 # actually acquired earlier labels in the preregistered trailing window.
 for forecast in forecasts[24:]:
  origin=instant(forecast.to_dict()['issued_at']);fit=fit_two_part(forecasts,observations,cutoff=origin,fitted_at=origin,policy=POLICY)
  assert fit['status']=='fitted'
  assert all(instant(r.to_dict()['available_at'])<=origin for r in observations if r.to_dict()['observation_sha256'] in {p['observation_sha256'] for p in fit['model']['training_pairs']})
  issues.append(make_issue(forecast,model=fit['model'],observation_cohort_sha256=cohort,policy=POLICY,prepared_at=prepared,mode='causal_retrospective_experiment'))
 result=api().evaluate_rain(forecasts,observations,assessed_at=prepared+timedelta(hours=1),policy=POLICY,issues=issues);group=next(iter(result['cohorts'].values()))
 assert group['outer']['independent_dates']==12 and group['outer']['wet_targets']==group['outer']['below_threshold_targets']==6
 assert group['candidate']['outer']['occurrence']['brier']<group['candidate']['outer']['training_only_climatology']['brier']
 assert group['candidate']['coverage']['predicted_targets']==12
 assert group['eligible_for_review'] is True and group['disposition']=='adopt_candidate'
 assert group['selected'] is result['as_issued_score'] is result['probability_calibration_qualified'] is False
