"""Procedure comparisons weight real targets/dates and keep artifact diagnostics separate."""
from dataclasses import asdict,replace
from datetime import timedelta
from math import sqrt
import pytest
from test_probabilistic import frame,POLICY
from weather_learning.contracts import identity,instant


def record(day,error,*,hour=0,offset=0,model='d'*64,cohort='b'*64):
 f=frame(day,hour,baseline=float(error),p10=None,p50=None,p90=None,cohort_sha256=cohort)
 if offset:f=replace(f,origin=(instant(f.origin)+timedelta(minutes=offset)).isoformat())
 def metrics(value):return dict(absolute_error=value,signed_error=value,p10_pinball=None,p90_pinball=None,interval_score_80=None,covered_80=None,width_80=None,wis=None,crps=None)
 value=dict(schema='earthship-confirmed-production-weather-score/v1',status='scored',forecast=asdict(f),
  observation=dict(kind='temperature',target_start=f.target_start,target_end=f.target_end,value=0.,available_at=(instant(f.target_end)+timedelta(minutes=3)).isoformat(),observation_sha256='a'*64,observation_policy_sha256='c'*64,quality={'synthetic_unit_fixture':True}),
  emission_sha256=identity(dict(day=day,hour=hour,offset=offset)),issue_sha256='a'*64,row_sha256='b'*64,model_sha256=model,bundle_sha256='f'*64,
  method_family='empirical',procedure_sha256='1'*64,training_policy_sha256=POLICY['policy_sha256'],scoring_runtime_sha256='2'*64,
  production_prediction_sha256='4'*64,published_at=(instant(f.origin)+timedelta(seconds=1)).isoformat(),raw=metrics(error),local=metrics(error/2),
  measurement_cohort_compatible=True,fallback_reason=None,issued_prediction_used=True,model_retrained=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
 value['score_sha256']=identity(value);return value


def test_each_target_and_local_date_has_equal_weight_despite_repeated_forecast_origins():
 from weather_learning.production_reporting import summarize_production_scores
 values=[record(1,0),record(1,4,offset=5),record(1,10,hour=1),record(2,6)]
 result=summarize_production_scores(values,policy=POLICY);group=result['cohorts'][0]
 assert group['support']==dict(pairs=4,targets=3,local_dates=2)
 assert group['raw']['mae']==pytest.approx(6) and group['active_policy']['mae']==pytest.approx(3)
 assert group['raw']['rmse']==pytest.approx(sqrt(45))
 assert result['local_coverage_qualified'] is False and result['population']=='confirmed_original_production_hourly_outputs'


def test_ordinary_refit_models_share_only_their_procedure_report_and_keep_own_artifact_scores():
 from weather_learning.production_reporting import summarize_production_scores
 result=summarize_production_scores([record(1,2),record(2,8,model='e'*64)],policy=POLICY)
 group=result['cohorts'][0]
 assert group['procedure_sha256']=='1'*64 and len(group['artifact_diagnostics'])==2
 assert {a['model_sha256']:a['active']['mae'] for a in group['artifact_diagnostics']}=={'d'*64:1,'e'*64:4}
 assert group['active_policy']['mae']==2.5
 assert group['scientific_review']['probability_claim'] is False


def test_different_measurement_cohorts_never_pool_even_with_the_same_method_and_grid():
 from weather_learning.production_reporting import summarize_production_scores
 result=summarize_production_scores([record(1,2),record(2,8,cohort='3'*64)],policy=POLICY)
 assert len(result['cohorts'])==2
 assert sorted(c['active_policy']['mae'] for c in result['cohorts'])==[1,4]


def test_resealed_duplicate_records_cannot_inflate_procedure_support():
 from weather_learning.production_reporting import summarize_production_scores
 value=record(1,2)
 with pytest.raises(ValueError,match='duplicate'):summarize_production_scores([value,value],policy=POLICY)



def test_complete_28_day_hourly_window_keeps_every_daily_refit_diagnostic_under_report_cap():
 from production_capacity_fixture import production_window_records
 from weather_learning.production_reporting import summarize_production_scores,MAX_BYTES
 from weather_learning.contracts import canonical
 result=summarize_production_scores(production_window_records(POLICY),policy=POLICY)
 assert result['records']==32256 and len(result['cohorts'])==8
 assert sum(len(c['artifact_diagnostics']) for c in result['cohorts'])==224
 assert len(canonical(result))<MAX_BYTES-4096  # complete owner/report envelope fits too
 assert all(c['support']['pairs']==4032 for c in result['cohorts'])


def test_bounded_single_pass_record_stream_matches_original_list_scores():
 from weather_learning.production_reporting import summarize_production_scores
 records=[record(1,2),record(2,8)]
 expected=summarize_production_scores(records,policy=POLICY)
 assert summarize_production_scores((r for r in records),policy=POLICY)==expected


def test_record_stream_rejects_an_overlong_window_before_reading_unbounded_input(monkeypatch):
 import weather_learning.production_reporting as reporting
 monkeypatch.setattr(reporting,'MAX_RECORDS',2)
 visited=[]
 def rows():
  for i in range(10):visited.append(i);yield record(i+1,2)
 with pytest.raises(ValueError,match='bounded'):reporting.summarize_production_scores(rows(),policy=POLICY)
 assert len(visited)==3
