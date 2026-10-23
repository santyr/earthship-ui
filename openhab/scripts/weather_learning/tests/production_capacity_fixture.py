"""Synthetic capacity fixture, never accuracy or real-observation evidence."""
from pathlib import Path
from hashlib import sha256
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from weather_learning.contracts import identity
from weather_learning.probabilistic import ForecastInput


def production_window_records(policy):
 from weather_learning.production_scoring import scoring_runtime
 runtime=scoring_runtime()
 manifest={name:sha256(Path('openhab/scripts/weather_learning',name).read_bytes()).hexdigest() for name in ('production_scoring.py','production_emissions.py','probabilistic.py','probabilistic_evaluation.py','marginal_outcomes.py','probabilistic_retained.py','contracts.py')}
 rows=[]
 base=datetime(2026,1,16,tzinfo=timezone.utc)
 for day in range(28):
  for hour in range(24):
   end=base+timedelta(days=day,hours=hour)
   for kind in ('temperature','wind'):
    for lead in (2,48,120,240):
     cohort=identity(dict(kind=kind,lead=lead,synthetic=True));procedure=identity(dict(kind=kind,lead=lead,procedure=True));model=identity(dict(day=day,kind=kind,lead=lead,daily_refit=True))
     for version in range(6):
      origin=end-timedelta(hours=lead,seconds=version);key=identity(dict(day=day,hour=hour,kind=kind,lead=lead,version=version))
      frame=ForecastInput(kind=kind,origin=origin.isoformat(),initialized_at=(origin-timedelta(hours=9)).isoformat(),target_start=(end if kind=='temperature' else end-timedelta(hours=1)).isoformat(),target_end=end.isoformat(),baseline=2.,incumbent=None,incumbent_sha256=None,p10=0.,p50=2.,p90=4.,source_ready_at=(origin-timedelta(hours=1)).isoformat(),actual_source_available_at=(origin-timedelta(hours=1)).isoformat(),availability_basis='recorded_ingestion_availability',forecast_sha256=key,grid_sha256='a'*64,cohort_sha256=cohort,timezone='America/Denver')
      raw=dict(absolute_error=2.,signed_error=2.,p10_pinball=.1,p90_pinball=.3,interval_score_80=4.,covered_80=True,width_80=4.,wis=None,crps=None)
      active=dict(absolute_error=1.,signed_error=1.,p10_pinball=0.,p90_pinball=.2,interval_score_80=2.,covered_80=True,width_80=2.,wis=.2,crps=.3)
      score=dict(schema='earthship-confirmed-production-weather-score/v1',status='scored',forecast=asdict(frame),observation=dict(kind=kind,target_start=frame.target_start,target_end=frame.target_end,value=0.,available_at=(end+timedelta(minutes=2)).isoformat(),observation_sha256=key,observation_policy_sha256='c'*64,quality=dict(synthetic_workload_only=True)),emission_sha256=key,issue_sha256=key,row_sha256=key,production_prediction_sha256=key,model_sha256=model,bundle_sha256=model,method_family='temperature_normal' if kind=='temperature' else 'nonnegative',procedure_sha256=procedure,training_policy_sha256=policy['policy_sha256'],scoring_runtime_sha256='2'*64,published_at=(origin+timedelta(seconds=1)).isoformat(),raw=raw,local=active,measurement_cohort_compatible=True,fallback_reason=None,issued_prediction_used=True,model_retrained=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
      score['observation'].update(schema='earthship-original-marginal-observation/v1',unit='degC' if kind=='temperature' else 'm_s',measurement_health_qualified=kind=='temperature',physical_calibration_qualified=False,automatic_actuation=False)
      score.update(scoring_manifest=manifest,scoring_runtime=runtime,scoring_runtime_sha256=identity(runtime))
      score['score_sha256']=identity(score);rows.append(score)
 return rows
