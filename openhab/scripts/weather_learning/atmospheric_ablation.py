"""Bounded, chronological matched feature ablations; no production selection."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from math import ceil,expm1,fsum,hypot,log1p,sqrt
from random import Random
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite,digest
from .evidence import utc

GROUPS={'dewpoint':1,'pressure':1,'wind_direction':2,'cloud_layers':3}
FIELDS=set('schema kind origin target_at lead_hours baseline outcome base_features groups feature_sha256 forecast_sha256 measurement_sha256 outcome_available_at source_ready_at source_available_at cohort_sha256 source_class parent_pair_sha256 automatic_actuation pair_sha256'.split())
METHODS={'residual':'date_target_weighted_bounded_ridge_residual/v1','wind_gain':'date_target_weighted_gain_prior24/v1','wind_log':'bounded_affine_log1p_scalar_wind/v1'}


def validate_rows(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded atmospheric ablation population required')
    seen=set();truth={}
    for r in rows:
        if (not isinstance(r,dict) or set(r)!=FIELDS or r['schema']!='earthship-atmospheric-ablation-pair/v1' or
                r['pair_sha256']!=identity({k:v for k,v in r.items() if k!='pair_sha256'}) or r['pair_sha256'] in seen or
                r['kind'] not in ('temperature','wind','thermal') or r['automatic_actuation'] is not False or
                r['source_class'] not in ('historical_assumed_availability','recorded_ingestion_availability')):raise ValueError('unique original-bound ablation pair required')
        seen.add(r['pair_sha256'])
        for k in ('pair_sha256','feature_sha256','forecast_sha256','measurement_sha256','cohort_sha256','parent_pair_sha256'):digest(r[k])
        origin,target=map(instant,(r['origin'],r['target_at']));ready,available=map(instant,(r['source_ready_at'],r['source_available_at']))
        if (not ready<=origin<target or not finite(r['lead_hours']) or (target-origin).total_seconds()!=r['lead_hours']*3600 or
                not 0<r['lead_hours']<=360 or instant(r['outcome_available_at'])<target or
                r['source_class']=='recorded_ingestion_availability' and available>origin):raise ValueError('original decision and measurement availability required')
        low,high=(-100,70) if r['kind']=='temperature' else (-40,140) if r['kind']=='thermal' else (0,200)
        if (any(not finite(r[k]) or not low<=r[k]<=high for k in ('baseline','outcome')) or not isinstance(r['base_features'],list) or
                len(r['base_features'])!=({'temperature':7,'wind':1,'thermal':6}[r['kind']]) or any(not finite(v) or abs(v)>1e5 for v in r['base_features']) or
                not isinstance(r['groups'],dict) or set(r['groups'])!=set(GROUPS)):raise ValueError('bounded original forecast predictors required')
        for name,count in GROUPS.items():
            x=r['groups'][name]
            if x is None:continue
            lo,hi=(-100,70) if name=='dewpoint' else (400,1200) if name=='pressure' else (-1,1) if name=='wind_direction' else (0,1)
            if not isinstance(x,list) or len(x)!=count or any(not finite(v) or not lo<=v<=hi for v in x) or name=='wind_direction' and abs(hypot(*x)-1)>1e-9:raise ValueError('native atmospheric group feature domain differs')
        key=(r['kind'],r['cohort_sha256'],r['target_at']);observation=(r['outcome'],r['measurement_sha256'],r['outcome_available_at'])
        if key in truth and truth[key]!=observation:raise ValueError('conflicting measured target cannot inflate support')
        truth[key]=observation
    return sorted(rows,key=lambda r:(r['origin'],r['target_at'],r['pair_sha256']))


def _date(r,zone):return instant(r['target_at']).astimezone(zone).date()
def _support(rows,zone):return dict(pairs=len(rows),targets=len({r['target_at'] for r in rows}),local_dates=len({_date(r,zone) for r in rows}))
def _weights(rows,zone):
    days=defaultdict(set);counts=Counter(r['target_at'] for r in rows)
    for r in rows:days[_date(r,zone)].add(r['target_at'])
    return [1/(len(days)*len(days[_date(r,zone)])*counts[r['target_at']]) for r in rows]


def _metrics(rows,key,zone):
    support=_support(rows,zone)
    if not rows:return dict(support=support,mae=None,rmse=None,bias=None,absolute_error_p95=None)
    weights=_weights(rows,zone);errors=[r[key]-r['outcome'] for r in rows];mass=0;p95=None
    for error,weight in sorted(zip(map(abs,errors),weights)):
        mass+=weight
        if mass>=.95-1e-12:p95=error;break
    return dict(support=support,mae=fsum(w*abs(e) for w,e in zip(weights,errors)),rmse=sqrt(fsum(w*e*e for w,e in zip(weights,errors))),bias=fsum(w*e for w,e in zip(weights,errors)),absolute_error_p95=p95)


def _eligible(rows,cutoff,maximum_days):
    earliest=cutoff-timedelta(days=maximum_days)
    return [r for r in rows if earliest<=instant(r['target_at'])<cutoff and (r['source_class']=='historical_assumed_availability' or instant(r['outcome_available_at'])<cutoff)]

def _enough(rows,zone,protocol):
    s=_support(rows,zone);t=protocol['temporal']
    return s['targets']>=t['minimum_training_targets'] and s['local_dates']>=t['minimum_training_local_dates']

def _vector(r,group):return r['base_features']+([] if group is None else r['groups'][group])


def _solve(rows,family,group,ridge,zone,policy):
    import numpy as np
    weights=np.asarray(_weights(rows,zone),dtype=float)
    if family=='wind_gain':
        xx=fsum(w*r['baseline']**2 for w,r in zip(weights,rows));xy=fsum(w*r['baseline']*r['outcome'] for w,r in zip(weights,rows))
        prior=xx*policy['candidates']['wind_gain_prior_targets']/_support(rows,zone)['targets'];lo,hi=policy['candidates']['wind_gain_bounds']
        return dict(gain=1. if xx==0 else max(lo,min(hi,(xy+prior)/(xx+prior))),centers=[],scales=[],coefficients=[],intercept=0.)
    matrix=np.asarray([_vector(r,group) for r in rows],dtype=float);target=np.asarray([log1p(r['outcome']) if family=='wind_log' else r['outcome']-r['baseline'] for r in rows])
    centers=np.average(matrix,axis=0,weights=weights);scales=np.sqrt(np.average((matrix-centers)**2,axis=0,weights=weights));scales=np.where(scales>1e-12,scales,1.)
    x=(matrix-centers)/scales;intercept=float(np.average(target,weights=weights));coefficients=np.linalg.solve(x.T@(weights[:,None]*x)+ridge*np.eye(x.shape[1]),x.T@(weights*(target-intercept)))
    if not np.isfinite(coefficients).all():raise ValueError('nonfinite ablation fit')
    return dict(gain=None,centers=centers.tolist(),scales=scales.tolist(),coefficients=coefficients.tolist(),intercept=intercept)


def _calculate(model,r,policy):
    if model['family']=='wind_gain':return r['baseline']*model['gain']
    x=_vector(r,model['group']);value=model['intercept']+fsum(c*(v-center)/scale for c,v,center,scale in zip(model['coefficients'],x,model['centers'],model['scales']))
    if model['family']=='wind_log':return expm1(max(0.,min(log1p(200),value)))
    limit=policy['candidates']['temperature_correction_limit_c' if r['kind']=='temperature' else 'thermal_correction_limit_f']
    return r['baseline']+max(-limit,min(limit,value))


def _fit(rows,*,family,group,cutoff,policy,protocol,zone,completed_at=None,guard=lambda:None):
    if family not in METHODS or group not in (None,*GROUPS) or family=='wind_gain' and group is not None:raise ValueError('one declared candidate family/group required')
    if len({(r['kind'],r['cohort_sha256'],r['source_class']) for r in rows})>1:raise ValueError('one coherent target/source population per fit required')
    if rows and ((rows[0]['kind']=='wind')!=(family in ('wind_gain','wind_log'))):raise ValueError('candidate family does not match target')
    selected=[r for r in rows if group is None or r['groups'][group] is not None];train=_eligible(selected,cutoff,protocol['temporal']['maximum_training_days'])
    if not _enough(train,zone,protocol):return None
    dates=sorted({_date(r,zone) for r in train});inner_dates=set(dates[-ceil(len(dates)/3):]);inner=[r for r in train if _date(r,zone) in inner_dates]
    inner_cutoff=min(instant(r['origin']) for r in inner)-timedelta(minutes=policy['fitting']['assumed_fit_latency_minutes'])
    earlier=_eligible([r for r in train if _date(r,zone) not in inner_dates],inner_cutoff,protocol['temporal']['maximum_training_days'])
    ridge=policy['fitting']['cold_inner_selection_ridge'];scores={}
    if family!='wind_gain' and _enough(earlier,zone,protocol):
        for candidate in policy['fitting']['ridge_candidates']:
            guard();fit=_solve(earlier,family,group,candidate,zone,policy);fit.update(family=family,group=group)
            scored=[dict(r,predicted=_calculate(fit,r,policy)) for r in inner];scores[str(candidate)]=_metrics(scored,'predicted',zone)['mae']
        ridge=min(policy['fitting']['ridge_candidates'],key=lambda r:(scores[str(r)],-r))
    guard();fit=_solve(train,family,group,ridge,zone,policy);completed=datetime.now(timezone.utc) if completed_at is None else utc(completed_at)
    if completed<cutoff:raise ValueError('actual completion cannot precede training cutoff')
    model=dict(schema='earthship-atmospheric-ablation-model/v1',method=METHODS[family],family=family,group=group,kind=train[0]['kind'],cohort_sha256=train[0]['cohort_sha256'],source_class=train[0]['source_class'],
        cutoff=cutoff.isoformat(),completed_at=completed.isoformat(),training_end=max(r['target_at'] for r in train),actual_training_availability_end=max(r['outcome_available_at'] for r in train),
        training_assumption='retrospective_target_end_order' if train[0]['source_class']=='historical_assumed_availability' else 'original_measurement_availability_before_cutoff',
        support=_support(train,zone),training_pair_sha256s=sorted(r['pair_sha256'] for r in train),feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),
        ridge=ridge,inner_scores=scores,inner_cutoff=inner_cutoff.isoformat(),inner_training_targets=_support(earlier,zone)['targets'],**fit,
        prospective_score=False,physical_calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    model['model_sha256']=identity(model);return model


def fit_ablation(rows,*,family,group,cutoff,policy,protocol,timezone_name='America/Denver',completed_at=None):
    return _fit(validate_rows(rows),family=family,group=group,cutoff=utc(cutoff),policy=policy,protocol=protocol,zone=ZoneInfo(timezone_name),completed_at=completed_at)


def predict_ablation(model,row,*,policy):
    validate_rows([row])
    if (not isinstance(model,dict) or model.get('schema')!='earthship-atmospheric-ablation-model/v1' or
            model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or model.get('feature_policy_sha256')!=identity(policy) or
            any(model.get(k) is not False for k in ('prospective_score','physical_calibration_qualified','release_authorized','automatic_actuation')) or
            not instant(model['training_end'])<instant(model['cutoff'])<=instant(model['completed_at']) or
            model['kind']!=row['kind'] or model['cohort_sha256']!=row['cohort_sha256'] or model['source_class']!=row['source_class'] or
            model['method']!=METHODS.get(model['family'])):raise ValueError('original bounded retrospective ablation model required')
    if instant(model['cutoff'])+timedelta(minutes=policy['fitting']['assumed_fit_latency_minutes'])>instant(row['origin']):raise ValueError('candidate weights not ready at experiment origin')
    if model['source_class']=='recorded_ingestion_availability' and (instant(model['actual_training_availability_end'])>=instant(model['cutoff']) or model['training_assumption']!='original_measurement_availability_before_cutoff'):
        raise ValueError('recorded measurements unavailable before model cutoff')
    if model['group'] is not None and row['groups'][model['group']] is None:raise ValueError('native feature support unavailable')
    if any(not finite(v) for key in ('centers','scales','coefficients') for v in model[key]) or any(v<=0 for v in model['scales']):raise ValueError('finite frozen preprocessing required')
    if model['family']!='wind_gain' and not len(model['coefficients'])==len(model['centers'])==len(model['scales'])==len(_vector(row,model['group'])):raise ValueError('frozen feature dimensions required')
    return _calculate(model,row,policy)


def _paired(rows,zone,seed):
    dates=defaultdict(list)
    for r in rows:dates[_date(r,zone)].append(r)
    deltas=[]
    for date,values in sorted(dates.items()):
        targets=defaultdict(list)
        for r in values:targets[r['target_at']].append(abs(r['candidate']-r['outcome'])-abs(r['baseline_prediction']-r['outcome']))
        deltas.append(fsum(fsum(v)/len(v) for v in targets.values())/len(targets))
    ci=None
    if deltas:
        random=Random(seed);draws=sorted(fsum(random.choice(deltas) for _ in deltas)/len(deltas) for _ in range(128));ci=[draws[3],draws[124]]
    return dict(blocks=len(deltas),delta_mae_interval_95=ci,independence_qualified=False,probability_claim=False)


def _comparison(rows,zone,protocol,withheld,eligible):
    matched=[r for r in rows if r['both_fitted']];support=_support(matched,zone)
    def metrics(values):return dict(support=_support(values,zone),baseline=_metrics(values,'baseline_prediction',zone),candidate=_metrics(values,'candidate',zone))
    groups={}
    for axis,fn in [('lead',lambda r:str(r['lead_hours'])),('local_hour',lambda r:str(instant(r['target_at']).astimezone(zone).hour)),('season',lambda r:str((instant(r['target_at']).astimezone(zone).month%12)//3)),('supported_native_regime',lambda r:'group_present' if r['group_available'] else 'group_missing')]:
        split=defaultdict(list)
        for r in matched:split[fn(r)].append(r)
        groups[axis]={k:metrics(v) for k,v in sorted(split.items())}
    scores=metrics(matched);a,b=scores['baseline']['mae'],scores['candidate']['mae'];s=protocol['selection'];temporal=protocol['temporal']
    enough=support['targets']>=temporal['minimum_outer_targets'] and support['local_dates']>=temporal['minimum_outer_local_dates']
    improvement=None if a is None or a==0 else 1-b/a
    regressions=[]
    for axis,values in groups.items():
        for label,score in values.items():
            if score['support']['targets']<s['minimum_subgroup_targets']:continue
            x,y=score['baseline']['mae'],score['candidate']['mae']
            if y>x*(1+s['maximum_supported_subgroup_relative_regression'])+1e-12:regressions.append(dict(axis=axis,label=label,**score))
    gate=bool(enough and improvement is not None and improvement>=s['point_or_proper_score_relative_improvement'] and not regressions)
    return dict(outer_support=_support(rows,zone),eligible_feature_pairs=eligible,withheld=dict(withheld),matched=scores,fallback_inclusive=metrics(rows),by_subgroup=groups,
        paired_day_blocks=_paired(matched,zone,protocol['limits']['scenario_seed']),relative_improvement=improvement,supported_subgroup_regressions=regressions,
        candidate_meets_score_gate=gate,disposition='insufficient_evidence' if not enough else 'retain_incumbent',review_recommendation='review_candidate' if gate else 'retain_incumbent',
        prospective_score=False,physical_calibration_qualified=False,release_authorized=False,automatic_actuation=False)


def assess_ablation(rows,*,policy,protocol,timezone_name='America/Denver',guard=lambda:None,completed_at=None,cohort_contexts=None):
    rows=validate_rows(rows);zone=ZoneInfo(timezone_name);populations=defaultdict(list)
    for r in rows:populations[(r['kind'],r['source_class'],r['cohort_sha256'])].append(r)
    models={};cohorts=[];predictions=[]
    for (kind,source_class,cohort),values in sorted(populations.items()):
        context=None if cohort_contexts is None else cohort_contexts.get(cohort)
        if cohort_contexts is not None and (not isinstance(context,dict) or identity(context)!=cohort):raise ValueError('original cohort descriptor differs from target population')
        dates=sorted({_date(r,zone) for r in values});outer=set(dates[-ceil(len(dates)/3):]) if dates else set();scored=defaultdict(list);fits={};withheld=defaultdict(Counter)
        comparisons=[*GROUPS]+(['wind_challenger'] if kind=='wind' else [])
        def get(family,group,subset,cutoff,label):
            key=(family,group,cutoff,label)
            if key not in fits:
                model=_fit(subset,family=family,group=group,cutoff=cutoff,policy=policy,protocol=protocol,zone=zone,completed_at=completed_at,guard=guard);fits[key]=model
                if model is not None:models[model['model_sha256']]=model
            return fits[key]
        base_family='wind_log' if kind=='wind' else 'residual'
        for row in values:
            guard()
            if _date(row,zone) not in outer:continue
            ready=instant(row['origin'])-timedelta(minutes=policy['fitting']['assumed_fit_latency_minutes']);cadence=policy['fitting']['model_cutoff_cadence_hours']*3600;cutoff=datetime.fromtimestamp((ready.timestamp()//cadence)*cadence,timezone.utc)
            all_base=get(base_family,None,values,cutoff,'all');fallback=row['baseline'] if all_base is None else _calculate(all_base,row,policy)
            for name in comparisons:
                available=name=='wind_challenger' or row['groups'][name] is not None
                baseline=challenger=None
                if available:
                    subset=values if name=='wind_challenger' else [r for r in values if r['groups'][name] is not None]
                    baseline=get('wind_gain' if name=='wind_challenger' else base_family,None,subset,cutoff,name)
                    challenger=get(base_family,None if name=='wind_challenger' else name,subset,cutoff,name)
                else:withheld[name]['native_feature_group_unavailable']+=1
                both=baseline is not None and challenger is not None
                if available and not both:withheld[name]['past_training_support_unavailable']+=1
                out=dict(row,comparison=name,group_available=available,both_fitted=both,
                    baseline_prediction=_calculate(baseline,row,policy) if both else fallback,candidate=_calculate(challenger,row,policy) if both else fallback,
                    baseline_model_sha256=None if baseline is None else baseline['model_sha256'],candidate_model_sha256=None if challenger is None else challenger['model_sha256'])
                scored[name].append(out)
                predictions.append({k:out[k] for k in ('pair_sha256','kind','cohort_sha256','origin','target_at','comparison','baseline_prediction','candidate','baseline_model_sha256','candidate_model_sha256','both_fitted')})
        reports={name:_comparison(scored[name],zone,protocol,withheld[name],sum(1 for r in values if name=='wind_challenger' or r['groups'][name] is not None)) for name in comparisons}
        cohorts.append(dict(kind=kind,source_class=source_class,cohort_sha256=cohort,context=context,unit={'temperature':'degC','thermal':'degF','wind':'m_s'}[kind],base_support=_support(values,zone),outer_target_dates=[d.isoformat() for d in sorted(outer)],comparisons=reports))
    result=dict(schema='earthship-atmospheric-ablation-assessment/v1',feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),cohorts=cohorts,models=list(models.values()),predictions=predictions,
        retrospective_only=True,physical_calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    result['assessment_sha256']=identity(result);return result
