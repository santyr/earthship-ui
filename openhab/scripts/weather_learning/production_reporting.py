"""Procedure and artifact metrics from immutable actual production scores."""
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from hashlib import sha256
from datetime import timedelta
from random import Random
from math import fsum
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant,digest,finite
from .probabilistic import ForecastInput,CalibrationPair,_policy,_weights,_lead
from .probabilistic_evaluation import _metrics,SEASONS

MAX_RECORDS=40000
# Full 28-day/48-row hourly workload with224 retained daily-refit artifacts
# measures563317 bytes. Keep the complete report with~16% headroom.
MAX_BYTES=640*1024


def _entry(value):
    if (not isinstance(value,dict) or value.get('schema')!='earthship-confirmed-production-weather-score/v1' or
            value.get('score_sha256')!=identity({k:v for k,v in value.items() if k!='score_sha256'}) or value.get('issued_prediction_used') is not True or
            any(value.get(k) is not False for k in ('model_retrained','local_coverage_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('unchanged original production score required')
    if value.get('status')!='scored':return None
    args=dict(value['forecast']);pin=args.pop('input_sha256');frame=ForecastInput(**args);observation=value['observation'];ready=instant(observation['available_at'])
    if (frame.input_sha256!=pin or (observation['kind'],observation['target_start'],observation['target_end'])!=(frame.kind,frame.target_start,frame.target_end) or
            not instant(frame.origin)<=instant(value['published_at'])<instant(frame.target_end) or
            frame.kind=='wind' and instant(value['published_at'])>instant(frame.target_start) or
            not instant(frame.target_end)<=ready<=instant(frame.target_end)+timedelta(days=7) or not finite(observation['value'])):
        raise ValueError('original published target and timely observation required')
    pair=CalibrationPair(forecast=frame,value=observation['value'],outcome_ready_at=ready.isoformat(),actual_outcome_available_at=ready.isoformat(),receipt_sha256=observation['observation_sha256'])
    digest(observation['observation_policy_sha256'])
    for key in ('procedure_sha256','training_policy_sha256','scoring_runtime_sha256','model_sha256'):
        if value.get(key) is not None:digest(value[key])
    base=value['raw'];local=value['local']
    if not isinstance(base,dict) or not finite(base.get('absolute_error')) or base['absolute_error']<0:raise ValueError('original raw point score required')
    if local is not None and (not isinstance(local,dict) or not finite(local.get('absolute_error')) or local['absolute_error']<0):raise ValueError('original local point score required')
    # The original hash was verified above. Reporting retains only grouping and
    # artifact metadata, never duplicate per-row producer manifests/runtime blobs.
    metadata={k:value.get(k) for k in ('model_sha256','method_family','procedure_sha256','training_policy_sha256','scoring_runtime_sha256')}
    return dict(pair=pair,baseline=base,candidate=base if local is None else local,both=local is not None,record=metadata)


def _brief(rows):
    metrics=_metrics(rows)
    fields=('mae','interval_score_80','coverage_80','width_80')
    return dict(support=metrics['support'],raw={k:metrics['baseline'][k] for k in fields},active={k:metrics['candidate'][k] for k in fields},
        raw_metric_support={k:metrics['baseline']['metric_support'][k] for k in ('mae','interval_score_80')},
        active_metric_support={k:metrics['candidate']['metric_support'][k] for k in ('mae','interval_score_80')})


def _subgroups(rows):
    axes={'lead':lambda e:'-'.join(map(str,_lead(e['pair'].forecast.origin,e['pair'].forecast.target_end)))+'h',
        'local_hour':lambda e:str(instant(e['pair'].forecast.target_end).astimezone(ZoneInfo(e['pair'].forecast.timezone)).hour),
        'season':lambda e:SEASONS[(instant(e['pair'].forecast.target_end).astimezone(ZoneInfo(e['pair'].forecast.timezone)).month%12)//3],
        'native_regime':lambda e:'zero' if e['pair'].forecast.baseline==0 else 'positive' if e['pair'].forecast.baseline>0 else 'negative',
        'outcome_regime':lambda e:'zero' if e['pair'].value==0 else 'positive' if e['pair'].value>0 else 'negative'}
    result={}
    for name,key in axes.items():
        groups=defaultdict(list)
        for row in rows:groups[key(row)].append(row)
        result[name]={label:_brief(subset) for label,subset in sorted(groups.items())}
    return result


def _scientific(rows,matched,subgroups,policy):
    kind=rows[0]['pair'].forecast.kind;primary='interval_score_80' if kind=='temperature' else 'mae'
    raw,active=matched['baseline'][primary],matched['candidate'][primary];support=matched['support'];gate=policy['qualification'];temporal=policy['temporal']
    improvement=None if raw is None or raw<=0 or active is None else 1-active/raw;regressions=[]
    for axis,groups in subgroups.items():
        for label,value in groups.items():
            for metric in sorted(set(('mae',primary))):
                if value['raw_metric_support'][metric]['targets']<gate['minimum_subgroup_targets']:continue
                a,b=value['raw'][metric],value['active'][metric]
                if a is not None and b is not None and b>a*(1+gate['maximum_supported_subgroup_regression'])+1e-12:
                    regressions.append(dict(axis=axis,label=label,metric=metric,raw=a,active=b))
    enough=support['targets']>=temporal['minimum_outer_targets'] and support['local_dates']>=temporal['minimum_outer_local_dates']
    blocks=defaultdict(list)
    for row in rows:
        if not row['both']:continue
        field='absolute_error' if primary=='mae' else primary;a,b=row['baseline'].get(field),row['candidate'].get(field)
        if a is None or b is None:continue
        f=row['pair'].forecast;day=instant(f.target_end).astimezone(ZoneInfo(f.timezone)).date().isoformat();blocks[day].append((row,b-a))
    values=[fsum(w*delta for w,(_,delta) in zip(_weights([row['pair'] for row,_ in group]),group)) for group in blocks.values()];interval=None
    if values:
        bootstrap=policy['scores']['paired_date_bootstrap'];rng=Random(bootstrap['seed'])
        draws=sorted(fsum(rng.choice(values) for _ in values)/len(values) for _ in range(bootstrap['replications']));interval=[draws[3],draws[124]]
    return dict(primary_metric=primary,relative_improvement=improvement,sufficient_target_date_support=enough,
        meets_original_score_criteria=bool(enough and improvement is not None and improvement>=gate['minimum_relative_improvement'] and not regressions),
        supported_subgroup_regressions=regressions,paired_local_date_blocks=len(values),paired_date_candidate_minus_raw_interval_95=interval,
        independence_qualified=False,reference='native_boundary_mean_hour_approximation_without_native_hourly_quantiles' if kind=='wind' else 'original_raw_native_temperature_mean_and_available_intervals',
        wind_point_only_comparison=kind=='wind',deployment_gate=False,probability_claim=False)


def summarize_production_scores(records,*,policy,guard=lambda:None):
    policy=_policy(policy)
    if not isinstance(records,(list,Iterator)) or isinstance(records,list) and len(records)>MAX_RECORDS:raise ValueError('bounded complete production score window required')
    seen=set();groups=defaultdict(list);incompatible=count=0
    for count,value in enumerate(records,1):
        guard()
        if count>MAX_RECORDS or not isinstance(value,dict):raise ValueError('bounded complete production score window required')
        pin=value.get('score_sha256')
        if pin in seen:raise ValueError('duplicate original production score')
        seen.add(pin);entry=_entry(value)
        if entry is None:incompatible+=1;continue
        f=entry['pair'].forecast;o=value['observation']
        # An older score lacking procedure metadata remains artifact-only;
        # unknown procedures are never pooled or attributed to new weights.
        procedure=value.get('procedure_sha256');legacy=value.get('model_sha256') if procedure is None else None
        key=(f.kind,f.cohort_sha256,f.grid_sha256,identity(o['quality']),o['observation_policy_sha256'],procedure or '',legacy or '',value.get('scoring_runtime_sha256') or '')
        groups[key].append(entry)
    cohorts=[]
    for key,rows in sorted(groups.items()):
        guard();metrics=_metrics(rows);matched=_metrics([r for r in rows if r['both']]);subgroups=_subgroups([r for r in rows if r['both']]);artifacts=defaultdict(list)
        for row in rows:
            if row['both'] and row['record']['model_sha256'] is not None:artifacts[row['record']['model_sha256']].append(row)
        diagnostics=[]
        for pin,subset in sorted(artifacts.items()):
            values=_metrics(subset);diagnostics.append(dict(model_sha256=pin,support=values['support'],raw=values['baseline'],active=values['candidate']))
        first=rows[0]['record'];cohorts.append(dict(kind=key[0],forecast_cohort_sha256=key[1],grid_sha256=key[2],observation_quality_sha256=key[3],observation_policy_sha256=key[4],
            procedure_sha256=first.get('procedure_sha256'),method_family=first.get('method_family'),training_policy_sha256=first.get('training_policy_sha256'),
            scoring_runtime_sha256=first.get('scoring_runtime_sha256'),aggregation_basis='registered_procedure_with_artifact_diagnostics' if key[5] else 'artifact_only_procedure_not_retained',
            unit={'temperature':'degC','wind':'m_s'}[key[0]],support=metrics['support'],raw=metrics['baseline'],active_policy=metrics['candidate'],
            matched=dict(support=matched['support'],raw=matched['baseline'],active=matched['candidate']),fallback_rows=sum(not r['both'] for r in rows),
            subgroups=subgroups,artifact_diagnostics=diagnostics,scientific_review=_scientific(rows,matched,subgroups,policy)))
    body=dict(schema='earthship-production-weather-comparisons/v1',records=count,incompatible_records=incompatible,cohorts=cohorts,
        population='confirmed_original_production_hourly_outputs',weights='equal_local_target_dates_then_targets_then_original_forecast_origins_and_versions',
        assessment_policy_sha256=policy['policy_sha256'],aggregation_manifest={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('production_reporting.py','probabilistic.py','probabilistic_evaluation.py','contracts.py','evidence.py')},scientific_qualification_changed=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    if len(canonical(body))>MAX_BYTES:raise ValueError('bounded complete production comparison report exceeded')
    body['summary_sha256']=identity(body);return body
