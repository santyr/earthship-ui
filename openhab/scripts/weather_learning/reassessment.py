"""Paired target/time-block diagnostics; no selection or qualification grant.

Callers must select one documented measurement cohort and freeze original
predictions before using this analysis. All forecasts sharing an observation
remain together. Calendar support never becomes an independence claim.
"""
from datetime import datetime,timezone
from math import ceil,fsum,sqrt
from random import Random
from zoneinfo import ZoneInfo
from .contracts import digest,finite,identity,instant

SCHEMA='earthship-paired-model-reassessment/v1'
NAMES=('raw','incumbent','candidate')


def _at(value):
    if isinstance(value,str):return instant(value)
    if not isinstance(value,datetime) or value.tzinfo is None:raise ValueError('aware analysis clock required')
    return value.astimezone(timezone.utc)


def _normalize(rows):
    if not isinstance(rows,(list,tuple)) or len(rows)>50000:raise ValueError('bounded paired analysis population required')
    pairs={};targets={}
    for row in rows:
        if set(row)!={'target_at','issued_at','target_identity','forecast_identity','observed','predictions'}:raise ValueError('closed paired analysis row required')
        target,issued=map(_at,(row['target_at'],row['issued_at']))
        if not issued<target:raise ValueError('forecast issue/target clocks must be causal')
        key=row['target_identity'];forecast=digest(row['forecast_identity'])
        if not isinstance(key,str) or not 1<=len(key)<=256 or not finite(row['observed']):raise ValueError('finite original measured target required')
        if set(row['predictions'])!=set(NAMES) or any(not finite(v) for v in row['predictions'].values()):raise ValueError('identical common finite prediction population required')
        target_key=target.isoformat(),key
        value=dict(target_at=target.isoformat(),issued_at=issued.isoformat(),target_identity=key,forecast_identity=forecast,
            observed=row['observed'],predictions=dict(row['predictions']))
        old=targets.setdefault(target_key,row['observed'])
        if old!=row['observed']:raise ValueError('conflicting shared measured target')
        # A different receipt cannot split a physical timestamp into extra support.
        for_time=targets.setdefault((target.isoformat(),'__receipt__'),key)
        if for_time!=key:raise ValueError('conflicting measured-target receipt identity')
        pair_key=target.isoformat(),key,issued.isoformat(),forecast
        if pair_key in pairs and pairs[pair_key]!=value:raise ValueError('conflicting original prediction for shared target')
        pairs[pair_key]=value
    return sorted(pairs.values(),key=lambda r:(r['target_at'],r['target_identity'],r['issued_at']))


def _cluster(rows):
    groups={}
    for row in rows:groups.setdefault((row['target_at'],row['target_identity']),[]).append(row)
    result=[]
    for (at,key),values in sorted(groups.items()):
        n=len(values);losses={}
        for name in NAMES:
            errors=[r['predictions'][name]-r['observed'] for r in values]
            losses[name]=dict(absolute=fsum(abs(e) for e in errors)/n,squared=fsum(e*e for e in errors)/n,
                bias=fsum(errors)/n,absolute_values=[(abs(e),1/n) for e in errors])
        result.append(dict(at=_at(at),identity=key,losses=losses))
    return result


def _metrics(clusters):
    result={};n=len(clusters)
    for name in NAMES:
        rows=[c['losses'][name] for c in clusters]
        tail=sorted((e,w/n) for r in rows for e,w in r['absolute_values']);mass=0.;p95=tail[-1][0]
        for error,weight in tail:
            mass+=weight
            if mass>=.95-1e-12:p95=error;break
        result[name]=dict(mae=fsum(r['absolute'] for r in rows)/n,rmse=sqrt(fsum(r['squared'] for r in rows)/n),
            bias=fsum(r['bias'] for r in rows)/n,p95_absolute_error=p95)
    return result


def _dependence(clusters):
    # Correlation is measured at actual elapsed lags, never adjacent row numbers
    # across gaps. Sparse/constant residuals remain explicitly unestimated.
    errors={c['at'].timestamp():c['losses']['incumbent']['bias'] for c in clusters};diagnostics=[]
    for hours in (1,3,6,12,24,48,72,168,336):
        pairs=[(error,errors[at+hours*3600]) for at,error in errors.items() if at+hours*3600 in errors]
        if len(pairs)<8:continue
        a=fsum(x for x,y in pairs)/len(pairs);b=fsum(y for x,y in pairs)/len(pairs)
        aa=fsum((x-a)**2 for x,y in pairs);bb=fsum((y-b)**2 for x,y in pairs)
        rho=None if aa*bb<1e-20 else fsum((x-a)*(y-b) for x,y in pairs)/sqrt(aa*bb)
        diagnostics.append(dict(lag_hours=hours,pairs=len(pairs),correlation=rho))
    known=[r for r in diagnostics if r['correlation'] is not None]
    if not known:return dict(status='not_estimable',decorrelation_hours=None,diagnostics=diagnostics)
    positive=[r for r in known if r['correlation']>.2]
    last=max((r['lag_hours'] for r in positive),default=0)
    later=[r['lag_hours'] for r in known if r['lag_hours']>last and r['correlation']<=.2]
    if not later:return dict(status='right_censored_positive_dependence',decorrelation_hours=last or known[-1]['lag_hours'],diagnostics=diagnostics)
    return dict(status='estimated_on_observed_elapsed_lags',decorrelation_hours=min(later),diagnostics=diagnostics)


def _percentile(values,p):
    values=sorted(values);at=(len(values)-1)*p;left=int(at);right=min(left+1,len(values)-1)
    return values[left]+(at-left)*(values[right]-values[left])


def _blocks(clusters,hours,*,samples,seed,minimum_blocks,dependence_known):
    blocks={}
    for row in clusters:
        key=int(row['at'].timestamp()//(hours*3600));block=blocks.setdefault(key,dict(n=0,raw=0.,incumbent=0.,candidate=0.))
        block['n']+=1
        for name in NAMES:block[name]+=row['losses'][name]['absolute']
    values=[v for k,v in sorted(blocks.items())]
    if len(values)<minimum_blocks:
        return dict(blocks=len(values),intervals=None,reason='fewer_than_required_temporal_blocks',minimum_blocks=minimum_blocks)
    if not dependence_known:
        return dict(blocks=len(values),intervals=None,reason='residual_decorrelation_not_established',minimum_blocks=minimum_blocks)
    random=Random(seed);distributions={baseline:[] for baseline in ('raw','incumbent')}
    for i in range(samples):
        selected=[values[random.randrange(len(values))] for _ in values];n=sum(r['n'] for r in selected)
        for baseline in distributions:
            distributions[baseline].append(fsum(r['candidate']-r[baseline] for r in selected)/n)
    return dict(blocks=len(values),intervals={name:dict(lower=_percentile(vals,.025),upper=_percentile(vals,.975)) for name,vals in distributions.items()},
        reason=None,minimum_blocks=minimum_blocks,interval='paired_MAE_difference_percentile_95',samples=samples)


def paired_reassessment(rows,*,timezone_name='America/Denver',samples=1000,seed=20261020,minimum_blocks=4):
    zone=ZoneInfo(timezone_name)
    if type(samples) is not int or not 100<=samples<=2000 or type(seed) is not int or type(minimum_blocks) is not int or not 4<=minimum_blocks<=128:
        raise ValueError('bounded predeclared resampling context required')
    rows=_normalize(rows);clusters=_cluster(rows)
    support=dict(forecast_pairs=len(rows),unique_measured_targets=len(clusters),
        local_target_dates=len({c['at'].astimezone(zone).date() for c in clusters}),timezone=timezone_name,
        weighting='unit_measured_target_across_original_issued_forecasts')
    body=dict(schema=SCHEMA,input_sha256=identity(rows),support=support,
        qualification='retrospective_analysis_not_qualification_or_selection',automatic_actuation=False,
        metrics=None,paired={},uncertainty=dict(reason='no_common_qualified_targets'))
    if not rows:return body|dict(report_sha256=identity(body))
    metrics=_metrics(clusters);lead=max((_at(r['target_at'])-_at(r['issued_at'])).total_seconds()/3600 for r in rows)
    dependence=_dependence(clusters);hours=max(1,ceil(max(lead,dependence['decorrelation_hours'] or 0)))
    known=dependence['status']=='estimated_on_observed_elapsed_lags'
    sensitivity={name:_blocks(clusters,length,samples=samples,seed=seed,minimum_blocks=minimum_blocks,dependence_known=known)
        for name,length in (('half',max(1,hours/2)),('base',hours),('double',hours*2))}
    body.update(metrics=metrics,paired={f'candidate_vs_{name}':dict(mae_difference=metrics['candidate']['mae']-metrics[name]['mae'],
        relative_mae_gain=None if metrics[name]['mae']==0 else 1-metrics['candidate']['mae']/metrics[name]['mae']) for name in ('raw','incumbent')},
        uncertainty=dict(block_hours=hours,maximum_lead_hours=lead,dependence=dependence,
            base=sensitivity['base'],sensitivity=sensitivity,seed=seed,scope='nonoverlapping_UTC_elapsed_target_blocks_shared_observations_kept_together'))
    return body|dict(report_sha256=identity(body))
