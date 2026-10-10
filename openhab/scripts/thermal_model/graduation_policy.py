"""Predeclared numerical thermal graduation policy; no release authority.

Raw qualified evidence must be verified separately before registration or release.
This layer derives thresholds from development baselines and retains their exact
inputs so altered caps/support or retrospective threshold selection are refused.
"""
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import math
from statistics import NormalDist,mean,stdev
from uuid import UUID
from zoneinfo import ZoneInfo

SCHEMA='earthship-thermal-graduation-policy/v1'
CONFIDENCE=.95
NOMINAL_COVERAGE=.90
COVERAGE_PRECISION=.10
SITE=ZoneInfo('America/Denver')
CANDIDATE_FIELDS={'artifact_sha256','runtime_sha256','trained_through','created_at',
                  'active_parameter_count','sensor_epochs'}
INTERVAL_FIELDS={'development_start','development_end','holdout_start','holdout_end',
                 'prospective_start','prospective_end'}
RECORD_FIELDS={'issue_at','target_at','horizon_hours','regime',
               'persistence_error_f','recent_cycle_error_f'}


def _utc(value):
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value)
        except ValueError:raise ValueError('aware policy timestamp required') from None
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('aware policy timestamp required')
    return value.astimezone(timezone.utc)


def _finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('finite baseline evidence required')
    return float(value)


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _sha(value):
    import re
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('full frozen candidate/runtime digest required')
    return value


def _quantile(values,fraction):
    ordered=sorted(values);position=(len(ordered)-1)*fraction
    lower=math.floor(position);upper=math.ceil(position)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower)


def _baseline_caps(rows):
    columns=[[row[name] for row in rows] for name in ('persistence_error_f','recent_cycle_error_f')]
    z=NormalDist().inv_cdf((1+CONFIDENCE)/2)
    return dict(max_mae_f=min(mean(map(abs,values)) for values in columns),
        max_rmse_f=min(math.sqrt(mean(value*value for value in values)) for values in columns),
        max_abs_bias_f=min(abs(mean(values))+z*stdev(values)/math.sqrt(len(values)) for values in columns),
        max_mean_interval_width_f=2*min(_quantile(list(map(abs,values)),NOMINAL_COVERAGE) for values in columns))


def derive_policy(development,*,declared_at,intervals,candidate,regimes):
    """Derive caps without seeing release outcomes; never claim qualification.

    The statistical support floor addresses approximate 95 percent precision of
    a 90 percent coverage rate to ten percentage points. Independent day blocks
    also preserve the strict fit's two-days-per-active-parameter support floor.
    """
    if not isinstance(candidate,dict) or set(candidate)!=CANDIDATE_FIELDS:
        raise ValueError('exact frozen candidate metadata required')
    for name in ('artifact_sha256','runtime_sha256'):_sha(candidate[name])
    parameters=candidate['active_parameter_count']
    if type(parameters) is not int or not 1<=parameters<=64:
        raise ValueError('active parameter count invalid')
    epochs=candidate['sensor_epochs']
    if not isinstance(epochs,dict) or set(epochs)!={'air','mass','outdoor'}:
        raise ValueError('qualified frozen sensor epochs required')
    for epoch in epochs.values():
        if not isinstance(epoch,str) or str(UUID(epoch))!=epoch:
            raise ValueError('qualified sensor epoch invalid')
    if not isinstance(intervals,dict) or set(intervals)!=INTERVAL_FIELDS:
        raise ValueError('explicit development/holdout/prospective intervals required')
    declared=_utc(declared_at)
    times={key:None if value is None else _utc(value) for key,value in intervals.items()}
    if any(times[key] is None for key in INTERVAL_FIELDS-{'prospective_end'}):
        raise ValueError('complete policy intervals required')
    trained,created=map(_utc,(candidate['trained_through'],candidate['created_at']))
    if not (times['development_start']<times['development_end']<=trained<=created<=declared<
            times['holdout_start']<times['holdout_end']):
        raise ValueError('threshold declaration/training must precede untouched holdout')
    if (times['prospective_start']<created or times['prospective_start']<declared or
            times['prospective_end'] is not None and times['prospective_end']<=times['prospective_start']):
        raise ValueError('prospective interval must follow candidate freeze/declaration')
    if (not isinstance(regimes,list) or not regimes or len(regimes)>3 or
            any(value not in {'warm','shoulder','winter'} for value in regimes) or len(set(regimes))!=len(regimes)):
        raise ValueError('explicit supported thermal regimes required')
    if not isinstance(development,(tuple,list)) or not 1<=len(development)<=10000:
        raise ValueError('bounded independent development baseline evidence required')
    records=[];seen=set()
    for original in development:
        if not isinstance(original,dict) or set(original)!=RECORD_FIELDS:
            raise ValueError('closed baseline development record required')
        row=dict(original);issue,target=map(_utc,(row['issue_at'],row['target_at']))
        hours=row['horizon_hours']
        if type(hours) is not int or hours not in (1,6,12,24,48,72) or row['regime'] not in regimes:
            raise ValueError('supported development horizon/regime required')
        if (not times['development_start']<=issue<target<=times['development_end'] or
                abs((target-issue).total_seconds()-hours*3600)>1800):
            raise ValueError('development target outside elapsed horizon/interval')
        identity=(issue,target,hours)
        if identity in seen:raise ValueError('duplicate development evidence')
        seen.add(identity)
        row.update(issue_at=issue.isoformat(),target_at=target.isoformat())
        for name in ('persistence_error_f','recent_cycle_error_f'):row[name]=_finite(row[name])
        records.append(row)
    horizons=sorted({row['horizon_hours'] for row in records})
    if not {1,6,12,24}<=set(horizons):raise ValueError('all required horizons need development evidence')
    z=NormalDist().inv_cdf((1+CONFIDENCE)/2)
    count=max(2*parameters,math.ceil(z*z*NOMINAL_COVERAGE*(1-NOMINAL_COVERAGE)/COVERAGE_PRECISION**2))
    thresholds={};by_regime={};support={}
    for horizon in horizons:
        independent=[];previous=None
        for row in sorted((row for row in records if row['horizon_hours']==horizon),key=lambda row:_utc(row['issue_at'])):
            if previous is None or _utc(row['issue_at'])>=previous:
                independent.append(row);previous=_utc(row['target_at'])
        if len({_utc(row['issue_at']).astimezone(SITE).date() for row in independent})<count:
            raise ValueError('insufficient independent development days')
        daily=[];seen_days=set()
        for row in independent:
            day=_utc(row['issue_at']).astimezone(SITE).date()
            if day not in seen_days:daily.append(row);seen_days.add(day)
        thresholds[str(horizon)]={**_baseline_caps(daily),
            'min_independent_windows':count,'min_independent_days':count}
        by_regime[str(horizon)]={}
        support[str(horizon)]=dict(raw_count=sum(row['horizon_hours']==horizon for row in records),
            independent_windows=len(independent),independent_days=len({_utc(row['issue_at']).astimezone(SITE).date() for row in independent}))
        for regime in regimes:
            subset=[row for row in daily if row['regime']==regime]
            days=len({_utc(row['issue_at']).astimezone(SITE).date() for row in subset})
            if days<count:raise ValueError('insufficient independent regime development days')
            by_regime[str(horizon)][regime]={**_baseline_caps(subset),
                'min_independent_windows':count,'min_independent_days':count}
    body=dict(schema=SCHEMA,declared_at=declared.isoformat(),
        candidate=json.loads(_canonical(candidate)),intervals={key:None if value is None else value.isoformat() for key,value in times.items()},
        regimes=sorted(regimes),horizons=horizons,confidence_level=CONFIDENCE,
        nominal_interval_coverage=NOMINAL_COVERAGE,coverage_precision=COVERAGE_PRECISION,
        comparison_alpha=(1-CONFIDENCE)/(4*len(horizons)*(1+len(regimes))),
        required_skill_upper_bound_f=0,max_qualification_age_hours=24,
        sampling_policy='greedy_UTC_nonoverlap_then_first_issue_per_Denver_day',
        freshness_basis='qualified prospective outcome recency; original training age remains visible',
        thresholds=thresholds,thresholds_by_regime=by_regime,development_support=support,
        development=sorted(records,key=lambda row:(row['issue_at'],row['horizon_hours'])),
        derivation='baseline MAE/RMSE; baseline bias confidence bound; 90th absolute-error quantile width; independent-day precision and parameter support',
        source_qualification_required_before_registration=True,release_qualification_claimed=False)
    body['policy_sha256']=sha256(_canonical(body)).hexdigest()
    return body


def validate_policy(value):
    if not isinstance(value,dict):raise ValueError('versioned numerical policy required')
    supplied=dict(value);digest=supplied.pop('policy_sha256',None)
    if digest!=sha256(_canonical(supplied)).hexdigest():raise ValueError('policy content changed')
    try:
        expected=derive_policy(value['development'],declared_at=value['declared_at'],
            intervals=value['intervals'],candidate=value['candidate'],regimes=value['regimes'])
    except (KeyError,TypeError):raise ValueError('policy fields incomplete') from None
    if expected!=value:raise ValueError('policy differs from preregistered derivation')
    return value
