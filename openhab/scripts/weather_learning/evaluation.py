"""Chronological, day-weighted shadow evaluation; no automatic promotion.

Incumbent issues are comparison inputs only. They cannot enter fitting or local
features. Regime tags are diagnostic caller annotations until source-qualified
regime evidence is integrated; they do not satisfy release gates on their own.
"""
from bisect import bisect_left,bisect_right
from dataclasses import asdict,dataclass
from datetime import date,datetime,timedelta
import math
from zoneinfo import ZoneInfo

from .contracts import digest,finite,identity,instant
from .evidence import utc
from .features import TemperatureOutcome,training_pair
from .training import _pairs,TemperaturePredictor

REGIMES=('clear','cloudy','large_diurnal','cold_front','precipitation')


@dataclass(frozen=True)
class EvaluationPolicy:
    declared_at:datetime
    train_end:datetime
    holdout_start:datetime
    holdout_end:datetime
    embargo_hours:int=24
    minimum_relative_mae_gain:float=.1
    incumbent_max_age_hours:int=24
    persistence_max_age_hours:int=72


@dataclass(frozen=True)
class ChronologicalSplit:
    train:tuple
    holdout:tuple
    excluded:int


@dataclass(frozen=True)
class IncumbentForecast:
    issued_at:datetime
    available_at:datetime
    target_at:datetime
    value_c:float
    source_digest:str
    provider:str='openmeteo'


def _policy(policy):
    if not isinstance(policy,EvaluationPolicy):raise ValueError('explicit predeclared evaluation policy required')
    declared,train,start,end=map(utc,(policy.declared_at,policy.train_end,policy.holdout_start,policy.holdout_end))
    if type(policy.embargo_hours) is not int or not 1<=policy.embargo_hours<=360:
        raise ValueError('explicit bounded embargo required')
    if not declared<=start<end or start<train+timedelta(hours=policy.embargo_hours) or end-train>timedelta(days=366):
        raise ValueError('predeclared chronological train/embargo/holdout required')
    if not finite(policy.minimum_relative_mae_gain) or not 0<=policy.minimum_relative_mae_gain<=1:
        raise ValueError('predeclared finite improvement threshold required')
    for hours in (policy.incumbent_max_age_hours,policy.persistence_max_age_hours):
        if type(hours) is not int or not 1<=hours<=168:raise ValueError('bounded comparison age required')
    return {key:utc(value).isoformat() if isinstance(value,datetime) else value for key,value in asdict(policy).items()}


def chronological_split(pairs,policy):
    _policy(policy)
    if not isinstance(pairs,(list,tuple)) or len(pairs)>20000:raise ValueError('bounded pairs required')
    for pair in pairs:training_pair(pair.forecast,pair.outcome)
    pairs=_pairs(pairs,max((pair.outcome.available_at for pair in pairs),default=policy.holdout_end))
    train=[];holdout=[]
    for pair in pairs:
        if pair.outcome.available_at<=policy.train_end:train.append(pair)
        elif policy.holdout_start<=pair.forecast.issued_at and pair.outcome.target_at<policy.holdout_end:holdout.append(pair)
    return ChronologicalSplit(tuple(train),tuple(holdout),len(pairs)-len(train)-len(holdout))


def _metrics(rows):
    if not rows:return None
    days={}
    for error,day in rows:days.setdefault(day,[]).append(error)
    # Each target date has total weight one, independent of issue frequency.
    count=len(days)
    absolute=sorted(abs(error) for error,_ in rows)
    return dict(pairs=len(rows),target_dates=count,
        mae_c=sum(sum(abs(error) for error in errors)/len(errors) for errors in days.values())/count,
        rmse_c=math.sqrt(sum(sum(error**2 for error in errors)/len(errors) for errors in days.values())/count),
        bias_c=sum(sum(errors)/len(errors) for errors in days.values())/count,
        pair_absolute_error_p95_c=absolute[math.ceil(.95*len(absolute))-1])


def _incumbent(records):
    if not isinstance(records,(list,tuple)) or len(records)>20000:raise ValueError('bounded retained comparison issues required')
    unique={}
    for record in records:
        if not isinstance(record,IncumbentForecast) or record.provider!='openmeteo' or not finite(record.value_c):
            raise ValueError('original labeled incumbent comparison required')
        available,issued,target=map(utc,(record.available_at,record.issued_at,record.target_at))
        if not available<=issued<target:raise ValueError('original incumbent availability required')
        digest(record.source_digest)
        key=(issued,target)
        if key in unique and unique[key]!=record:raise ValueError('conflicting incumbent issue')
        unique[key]=record
    return tuple(unique.values())


def _outcomes(records):
    from weather_temperature_evidence import sensor_epoch_id
    if not isinstance(records,(list,tuple)) or len(records)>20000:raise ValueError('bounded qualified persistence outcomes required')
    unique={}
    for record in records:
        if not isinstance(record,TemperatureOutcome) or not finite(record.value_c):raise ValueError('qualified local outcome required')
        if not utc(record.target_at)<=utc(record.available_at)<=utc(record.assessed_at):raise ValueError('original outcome availability required')
        sensor_epoch_id(record.sensor_epoch);digest(record.receipt_digest)
        key=(record.sensor_epoch,record.target_at)
        prior=unique.get(key)
        if prior is not None and (prior.value_c,prior.receipt_digest)!=(record.value_c,record.receipt_digest):
            raise ValueError('conflicting local persistence outcome')
        unique[key]=record
    return tuple(unique.values())


def _horizon(forecast):
    hours=(forecast.target_at-forecast.issued_at).total_seconds()/3600
    return next(label for end,label in ((24,'0-24h'),(72,'24-72h'),(168,'72-168h'),(360,'168-360h')) if hours<=end)


def evaluate(model,holdout,policy,*,incumbent=(),prior_outcomes=(),regimes_by_day=None):
    frozen_policy=_policy(policy);predictor=TemperaturePredictor(model)
    if instant(model['cutoff'])>utc(policy.train_end):raise ValueError('model fit crosses declared train boundary')
    holdout=_pairs(holdout,utc(policy.holdout_end))
    if any(not policy.holdout_start<=pair.forecast.issued_at or pair.outcome.target_at>=policy.holdout_end for pair in holdout):
        raise ValueError('only declared holdout issues/targets may be evaluated')
    incumbent=_incumbent(incumbent)
    outcomes=_outcomes(list(prior_outcomes)+[pair.outcome for pair in holdout])
    tags={} if regimes_by_day is None else regimes_by_day
    if not isinstance(tags,dict) or len(tags)>366:raise ValueError('bounded diagnostic regime annotations required')
    for day,names in tags.items():
        if date.fromisoformat(day).isoformat()!=day or not isinstance(names,(list,tuple)) or not names or not set(names)<=set(REGIMES):
            raise ValueError('explicit known regime annotations required')
    local_index={}
    for record in outcomes:local_index.setdefault(record.sensor_epoch,[]).append(record)
    for epoch,records in local_index.items():
        records.sort(key=lambda record:record.target_at)
        local_index[epoch]=([record.target_at for record in records],records)
    incumbent_index={}
    for record in incumbent:incumbent_index.setdefault(record.target_at,[]).append(record)
    for target,records in incumbent_index.items():
        records.sort(key=lambda record:record.issued_at)
        incumbent_index[target]=([record.issued_at for record in records],records)
    all_scores={name:[] for name in ('raw','candidate','persistence')};horizons={};regimes={};comparison={'candidate':[],'incumbent':[]};originals=set()
    for pair in holdout:
        forecast,outcome=pair.forecast,pair.outcome
        day=outcome.target_at.astimezone(ZoneInfo(forecast.site_timezone)).date().isoformat()
        local=predictor.predict(forecast,sensor_epoch=outcome.sensor_epoch)['value_c']
        scores={'raw':forecast.mean_c-outcome.value_c,'candidate':local-outcome.value_c}
        times,records=local_index.get(outcome.sensor_epoch,([],[]))
        first=bisect_left(times,forecast.issued_at-timedelta(hours=policy.persistence_max_age_hours))
        last=bisect_right(times,forecast.issued_at)
        for index in range(last-1,first-1,-1):
            if records[index].available_at<=forecast.issued_at:
                scores['persistence']=records[index].value_c-outcome.value_c
                break
        times,records=incumbent_index.get(forecast.target_at,([],[]))
        index=bisect_right(times,forecast.issued_at)-1
        if index>=0 and records[index].issued_at>=forecast.issued_at-timedelta(hours=policy.incumbent_max_age_hours):
            original=records[index]
            comparison['candidate'].append((scores['candidate'],day));comparison['incumbent'].append((original.value_c-outcome.value_c,day))
            originals.add(original.source_digest)
        groups=[horizons.setdefault(_horizon(forecast),{})]
        groups.extend(regimes.setdefault(name,{}) for name in tags.get(day,('unclassified',)))
        for name,error in scores.items():
            all_scores[name].append((error,day))
            for group in groups:group.setdefault(name,[]).append((error,day))
    scored_comparison={name:_metrics(rows) for name,rows in comparison.items()}
    baseline=scored_comparison['incumbent'];candidate=scored_comparison['candidate']
    gain=(1-candidate['mae_c']/baseline['mae_c']) if baseline is not None and baseline['mae_c']>0 else None
    paired=dict(pairs=len(comparison['candidate']),**scored_comparison,relative_mae_gain=gain,
                predeclared_target_met=None if gain is None else gain>=policy.minimum_relative_mae_gain)
    report=dict(schema='earthship-weathernext-temperature-evaluation/v1',provider='weathernext3',qualification='SHADOW_ONLY',
        policy=frozen_policy,policy_sha256=identity(frozen_policy),model_sha256=model['artifact_sha256'],holdout_pairs=len(holdout),
        scoring_unit='equal_weight_per_local_target_date',scores={name:_metrics(rows) for name,rows in all_scores.items()},
        by_horizon={key:{name:_metrics(rows) for name,rows in group.items()} for key,group in sorted(horizons.items())},
        by_regime={key:{name:_metrics(rows) for name,rows in group.items()} for key,group in sorted(regimes.items())},
        regime_annotation_status='diagnostic_only',missing_regimes=sorted(set(REGIMES)-set(regimes)),paired_incumbent_comparison=paired,
        pair_manifest=[pair.pair_digest for pair in holdout],incumbent_originals=sorted(originals),
        missing_release_evidence=['prospective_acquisition','complete_training_days','untouched_holdout_days','prospective_shadow_inference','qualified_weather_regimes','required_variable_gates'],
        automatic_actuation=False)
    return report|{'report_sha256':identity(report)}
