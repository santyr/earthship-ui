"""Past-only rolling marginal evaluation. No fitted object is selected or issued.

Hyperparameters are chosen once from earlier inner dates, before the earliest
outer prediction origin. Later outer outcomes can enter a subsequent scheduled
refit only after their original availability, never the hyperparameter choice.
Scoring consumes literal fitted predictions, not a current model pointer.
"""
from collections import defaultdict,Counter
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from math import ceil,fsum,sqrt
from random import Random
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant,finite
from . import probabilistic as kernels

SEASONS=('winter','spring','summer','autumn')
METRICS=('mae','rmse','bias','absolute_error_p95','p10_pinball','p90_pinball','interval_score_80','coverage_80','width_80','wis','crps')


def score_retained_prediction(value,outcome):
    """Pure score of an original prediction; caller binds it to its saved receipt."""
    if (not isinstance(value,dict) or value.get('schema')!='earthship-local-marginal-prediction/v1' or
            value.get('prediction_sha256')!=identity({k:v for k,v in value.items() if k!='prediction_sha256'}) or
            value.get('quantile_levels')!=list(kernels.LEVELS) or len(value.get('quantiles',[]))!=5 or
            any(not finite(q) for q in value['quantiles']) or value['quantiles']!=sorted(value['quantiles']) or
            any(value.get(k) is not False for k in ('local_coverage_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('unchanged original retained marginal prediction required')
    obj=object.__new__(kernels.MarginalPrediction);object.__setattr__(obj,'_raw',canonical(value))
    return kernels.score_marginal(obj,outcome)


def _date(pair):
    f=pair.forecast
    return instant(f.target_end).astimezone(ZoneInfo(f.timezone)).date()


def _support(rows):return kernels._support([r['pair'] for r in rows])


def _raw_score(frame,value,*,incumbent=False):
    point=frame.incumbent if incumbent and frame.incumbent is not None else frame.baseline
    score=dict(absolute_error=abs(point-value),signed_error=point-value,p10_pinball=None,p90_pinball=None,interval_score_80=None,covered_80=None,width_80=None,wis=None,crps=None)
    if frame.width is not None:
        a,b=frame.p10,frame.p90
        score.update(p10_pinball=(.1-(value<a))*(value-a),p90_pinball=(.9-(value<b))*(value-b),
            interval_score_80=b-a+10*max(0,a-value)+10*max(0,value-b),covered_80=a<=value<=b,width_80=b-a)
    return score


def _aggregate(rows,side):
    result=dict(support=_support(rows));metric_support={}
    aliases=dict(mae='absolute_error',rmse='signed_error',bias='signed_error',absolute_error_p95='absolute_error',coverage_80='covered_80')
    for name in METRICS:
        field=aliases.get(name,name);usable=[r for r in rows if r[side].get(field) is not None];metric_support[name]=_support(usable)
        if not usable:result[name]=None;continue
        weights=kernels._weights([r['pair'] for r in usable]);values=[r[side][field] for r in usable]
        if name=='rmse':v=sqrt(fsum(w*x*x for w,x in zip(weights,values)))
        elif name=='absolute_error_p95':v=kernels._quantile(values,weights,.95)
        else:v=fsum(w*x for w,x in zip(weights,values))
        result[name]=v
    result['metric_support']=metric_support;return result


def _metrics(rows):return dict(support=_support(rows),baseline=_aggregate(rows,'baseline'),candidate=_aggregate(rows,'candidate'))


def _fit(rows,family,cutoff,parameter,policy,completed_at,guard):
    guard()
    if family=='adaptive':return kernels.fit_adaptive(rows,cutoff=cutoff,completed_at=completed_at,half_life_hours=parameter,policy=policy,retrospective=True)
    return kernels.fit_marginal(rows,family=family,cutoff=cutoff,completed_at=completed_at,policy=policy,ridge=parameter,retrospective=True,guard=guard)


def _select(rows,outer,policy,completed_at,guard,models):
    latency=timedelta(minutes=policy['temporal']['assumed_fit_latency_minutes']);cutoff=min(instant(r.forecast.origin) for r in outer)-latency
    train=kernels._eligible(rows,cutoff,True,policy);dates=sorted({_date(r) for r in train});inner_dates=set(dates[-ceil(len(dates)/3):]) if dates else set()
    inner=[r for r in train if _date(r) in inner_dates]
    inner_cutoff=min((instant(r.forecast.origin) for r in inner),default=cutoff)-latency
    earlier=kernels._eligible([r for r in train if _date(r) not in inner_dates],inner_cutoff,True,policy)
    support=kernels._support(inner);enough=(kernels._enough(earlier,policy) and support['targets']>=policy['temporal']['minimum_inner_targets'] and support['local_dates']>=policy['temporal']['minimum_inner_local_dates'])
    families=['empirical','temperature_normal','adaptive'] if rows[0].forecast.kind=='temperature' else ['empirical','nonnegative'];selections={}
    for family in families:
        options=[max(policy['optimization']['ridge_candidates'])] if family=='empirical' else policy['adaptive']['half_life_candidates_hours'] if family=='adaptive' else policy['optimization']['ridge_candidates']
        chosen=max(options);scores={};supports={}
        if enough and family!='empirical':
            for parameter in options:
                model=_fit(earlier,family,inner_cutoff,parameter,policy,completed_at,guard);scored=[]
                if model is not None:
                    body=model.to_dict();models[body['model_sha256']]=body
                    for r in inner:
                        guard()
                        if family=='adaptive':
                            prediction=kernels.adaptive_point(model,r.forecast,policy=policy,retrospective=True)
                            if prediction['candidate_used']:scored.append(dict(pair=r,score=abs(prediction['value']-r.value)))
                        else:
                            prediction=kernels.predict_marginal(model,r.forecast,policy=policy,retrospective=True)
                            if prediction is not None:scored.append(dict(pair=r,score=kernels.score_marginal(prediction,r.value)['interval_score_80']))
                supports[str(parameter)]=_support(scored)
                if supports[str(parameter)]['targets']>=policy['temporal']['minimum_inner_targets'] and supports[str(parameter)]['local_dates']>=policy['temporal']['minimum_inner_local_dates']:
                    scores[str(parameter)]=fsum(w*r['score'] for w,r in zip(kernels._weights([r['pair'] for r in scored]),scored))
        if scores:chosen=min((p for p in options if str(p) in scores),key=lambda p:(scores[str(p)],-p))
        selections[family]=dict(parameter=chosen,inner_scores=scores,inner_support_by_parameter=supports,
            reason='earlier_only_inner_score' if scores else 'empirical_no_tuning' if family=='empirical' else 'insufficient_inner_support_use_frozen_default')
    return dict(before_outer_origin=cutoff.isoformat(),inner_cutoff=inner_cutoff.isoformat(),inner_support=support,earlier_support=kernels._support(earlier),families=selections)


def _comparison(rows,*,primary,policy):
    matched=[r for r in rows if r['both']];metrics=_metrics(matched);groups={}
    axes=[('lead',lambda r:str((instant(r['pair'].forecast.target_end)-instant(r['pair'].forecast.origin)).total_seconds()/3600),()),
        ('local_hour',lambda r:str(instant(r['pair'].forecast.target_end).astimezone(ZoneInfo(r['pair'].forecast.timezone)).hour),map(str,range(24))),
        ('season',lambda r:SEASONS[(_date(r['pair']).month%12)//3],SEASONS),
        ('native_regime',lambda r:'zero' if r['pair'].forecast.baseline==0 else 'positive' if r['pair'].forecast.baseline>0 else 'negative',('zero','positive','negative')),
        ('outcome_regime',lambda r:'zero' if r['pair'].value==0 else 'positive' if r['pair'].value>0 else 'negative',('zero','positive','negative'))]
    for axis,fn,declared in axes:
        split={key:[] for key in declared}
        for r in matched:split.setdefault(fn(r),[]).append(r)
        groups[axis]={key:_metrics(values) for key,values in sorted(split.items())}
    s=metrics['support'];temporal=policy['temporal'];gate=policy['qualification'];a,b=metrics['baseline'][primary],metrics['candidate'][primary]
    improvement=None if a is None or a<=0 or b is None else 1-b/a
    enough=s['targets']>=temporal['minimum_outer_targets'] and s['local_dates']>=temporal['minimum_outer_local_dates'] and a is not None and b is not None
    regressions=[]
    for axis,values in groups.items():
        for label,value in values.items():
            if value['support']['targets']<gate['minimum_subgroup_targets']:continue
            for metric in sorted(set((primary,'mae'))):
                x,y=value['baseline'][metric],value['candidate'][metric]
                if x is not None and y is not None and y>x*(1+gate['maximum_supported_subgroup_regression'])+1e-12:regressions.append(dict(axis=axis,label=label,metric=metric,baseline=x,candidate=y,targets=value['support']['targets']))
    deltas=defaultdict(list)
    for r in matched:
        x,y=r['baseline'][{'mae':'absolute_error'}.get(primary,primary)],r['candidate'][{'mae':'absolute_error'}.get(primary,primary)]
        if x is not None and y is not None:deltas[_date(r['pair'])].append(dict(pair=r['pair'],delta=y-x))
    values=[]
    for day,group in sorted(deltas.items()):values.append(fsum(w*r['delta'] for w,r in zip(kernels._weights([r['pair'] for r in group]),group)))
    interval=None
    if values:
        bootstrap=policy['scores']['paired_date_bootstrap'];rng=Random(bootstrap['seed']);draws=sorted(fsum(rng.choice(values) for _ in values)/len(values) for _ in range(bootstrap['replications']));interval=[draws[3],draws[124]]
    score_gate=bool(enough and improvement is not None and improvement>=gate['minimum_relative_improvement'] and not regressions)
    coverage=metrics['candidate']['coverage_80'];coverage_review=bool(score_gate and s['local_dates']>=gate['minimum_local_date_blocks_for_probability_review'] and coverage is not None and abs(coverage-.8)<=gate['coverage80_absolute_tolerance_for_review'])
    return dict(primary_metric=primary,matched=metrics,fallback_inclusive=_metrics(rows),by_subgroup=groups,
        withheld=dict(Counter(r['reason'] for r in rows if r['reason'])),relative_improvement=improvement,supported_subgroup_regressions=regressions,
        paired_date_blocks=dict(blocks=len(values),candidate_minus_baseline_interval_95=interval,independence_qualified=False,probability_claim=False),
        candidate_meets_score_gate=score_gate,probability_review_support_only=coverage_review,
        disposition='insufficient_evidence' if not enough else 'retain_incumbent',review_recommendation='review_candidate' if score_gate else 'retain_incumbent',
        local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)


def assess_marginals(rows,*,policy,completed_at=None,guard=lambda:None):
    policy=kernels._policy(policy);rows=kernels._validate(rows);populations=defaultdict(list)
    for r in rows:populations[kernels._cohort(r.forecast)].append(r)
    models={};predictions=[];reports=[]
    for context,values in sorted(populations.items()):
        values=sorted(values,key=lambda r:(r.forecast.origin,r.forecast.target_end,r.pair_sha256));dates=sorted({_date(r) for r in values});outer_dates=set(dates[-ceil(len(dates)/3):]);outer=[r for r in values if _date(r) in outer_dates]
        selection=_select(values,outer,policy,completed_at,guard,models);fits={};comparisons=defaultdict(list)
        families=list(selection['families'])
        for row in outer:
            guard();f=row.forecast;origin=instant(f.origin);ready=origin-timedelta(minutes=policy['temporal']['assumed_fit_latency_minutes']);cadence=policy['temporal']['fit_frequency_hours']*3600;cutoff=datetime.fromtimestamp(ready.timestamp()//cadence*cadence,timezone.utc)
            local={};adaptive=None
            for family in families:
                key=(family,cutoff)
                if key not in fits:
                    model=_fit(values,family,cutoff,selection['families'][family]['parameter'],policy,completed_at,guard);fits[key]=model
                    if model is not None:
                        body=model.to_dict();models[body['model_sha256']]=body
                model=fits[key]
                if family=='adaptive':adaptive=kernels.adaptive_point(model,f,policy=policy,retrospective=True)
                else:
                    value=kernels.predict_marginal(model,f,policy=policy,retrospective=True);local[family]=None if value is None else value.to_dict()
            raw=_raw_score(f,row.value);scores={family:None if value is None else score_retained_prediction(value,row.value) for family,value in local.items()}
            definitions=[('temperature_normal_vs_raw','temperature_normal','raw'),('temperature_normal_vs_empirical','temperature_normal','empirical'),('empirical_vs_raw','empirical','raw'),('adaptive_vs_incumbent','adaptive','incumbent')] if f.kind=='temperature' else [('nonnegative_vs_empirical','nonnegative','empirical')]
            for name,candidate,baseline in definitions:
                bs=_raw_score(f,row.value,incumbent=True) if baseline=='incumbent' else raw if baseline=='raw' else scores.get(baseline)
                cs=None
                if candidate=='adaptive':
                    if adaptive['candidate_used']:cs=dict(_raw_score(f,row.value),absolute_error=abs(adaptive['value']-row.value),signed_error=adaptive['value']-row.value,interval_score_80=None,covered_80=None,width_80=None,p10_pinball=None,p90_pinball=None)
                else:cs=scores.get(candidate)
                base_ok=bs is not None and (candidate=='adaptive' or bs['interval_score_80'] is not None)
                both=base_ok and cs is not None
                reason='candidate_unavailable' if cs is None else 'baseline_unavailable' if not base_ok else None
                comparisons[name].append(dict(pair=row,baseline=bs if base_ok else raw,candidate=cs if both else bs if base_ok else raw,both=both,reason=reason))
            record=dict(schema='earthship-retrospective-marginal-prediction-record/v1',pair_sha256=row.pair_sha256,forecast=asdict(f),raw=dict(mean=f.baseline,p10=f.p10,p50=f.p50,p90=f.p90),marginals=local,adaptive=adaptive,issued=False,retrospective=True,local_coverage_qualified=False,automatic_actuation=False)
            record['record_sha256']=identity(record);predictions.append(record)
        reports.append(dict(kind=context[0],cohort_sha256=context[1],grid_sha256=context[2],timezone=context[3],lead_scope_hours=list(context[4]),availability_basis=context[5],support=kernels._support(values),outer_support=kernels._support(outer),selection=selection,
            comparisons={name:_comparison(group,primary='mae' if name=='adaptive_vs_incumbent' else 'interval_score_80',policy=policy) for name,group in comparisons.items()}))
    result=dict(schema='earthship-marginal-calibration-evaluation/v1',policy_sha256=policy['policy_sha256'],population_support=kernels._support(rows),cohorts=reports,models=models,predictions=predictions,
        retrospective=True,issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    result['evaluation_sha256']=identity(result);return result
