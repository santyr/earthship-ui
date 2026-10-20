"""Small fresh WeatherNext corrections. Fitting never reads incumbent state.

Artifacts are shadow candidates, never cutover approvals. `cutoff` is the as-of
fitting decision; the scheduled worker must use its actual current clock. These
pure routines also support explicitly retrospective chronological experiments.
"""
from datetime import timedelta
import json,math,re
from zoneinfo import ZoneInfo

from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .features import FEATURE_NAMES,feature_vector,training_pair,validate_target,unique_pairs
from .weights import temperature_weights,validate_support

SCHEMA='earthship-weathernext-temperature-model/v2'

FIELDS={'schema','provider','algorithm','grid_digest','sensor_epoch','site_timezone','code_revision','cutoff','training_start','training_end',
    'sample_count','target_dates','training_manifest','feature_names','feature_centers','feature_scales','coefficients',
    'intercept_c','max_correction_c','ridge','qualification','artifact_sha256'}


def _artifact(pairs,*,cutoff,code_revision,max_correction_c,algorithm,ridge):
    cutoff=utc(cutoff)
    if not isinstance(code_revision,str) or not re.fullmatch('[0-9a-f]{40}',code_revision):raise ValueError('immutable code revision required')
    if not finite(max_correction_c) or not 0<max_correction_c<=20:raise ValueError('finite bounded correction required')
    if not finite(ridge) or ridge<0:raise ValueError('finite nonnegative regularization required')
    pairs=unique_pairs(pairs,cutoff)
    manifest=[dict(pair_sha256=pair.pair_digest,snapshot_sha256=pair.forecast.snapshot_digest,issue_sha256=pair.forecast.issue_digest,
                   outcome_sha256=pair.outcome.receipt_digest,target_at=pair.outcome.target_at.isoformat(),issued_at=pair.forecast.issued_at.isoformat()) for pair in pairs]
    days={pair.outcome.target_at.astimezone(ZoneInfo(pair.forecast.site_timezone)).date() for pair in pairs}
    _,support=temperature_weights(pairs)
    return pairs,dict(schema=SCHEMA,support=support,provider='weathernext3',algorithm=algorithm,
        grid_digest=pairs[0].forecast.grid_digest if pairs else None,sensor_epoch=pairs[0].outcome.sensor_epoch if pairs else None,
        site_timezone=pairs[0].forecast.site_timezone if pairs else None,
        code_revision=code_revision,cutoff=cutoff.isoformat(),training_start=pairs[0].outcome.target_at.isoformat() if pairs else None,
        training_end=pairs[-1].outcome.target_at.isoformat() if pairs else None,sample_count=len(pairs),target_dates=len(days),
        training_manifest=manifest,feature_names=[],feature_centers=[],feature_scales=[],coefficients=[],intercept_c=0.,
        max_correction_c=float(max_correction_c),ridge=float(ridge),qualification='SHADOW_ONLY')


def fit_bias(pairs,*,cutoff,code_revision,max_correction_c=6):
    pairs,model=_artifact(pairs,cutoff=cutoff,code_revision=code_revision,max_correction_c=max_correction_c,algorithm='bounded_bias',ridge=0)
    if pairs:
        weights,support=temperature_weights(pairs)
        model['intercept_c']=math.fsum(w*(pair.outcome.value_c-pair.forecast.mean_c) for w,pair in zip(weights,pairs))/support['target_weight_sum']
    return model|{'artifact_sha256':identity(model)}


def _solve(matrix,values):
    """Pivoted elimination for the fixed seven-feature ridge system."""
    n=len(values);aug=[list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(n):
        pivot=max(range(column,n),key=lambda row:abs(aug[row][column]))
        aug[column],aug[pivot]=aug[pivot],aug[column]
        divisor=aug[column][column]
        if abs(divisor)<1e-12:raise ValueError('residual fit is numerically singular')
        aug[column]=[value/divisor for value in aug[column]]
        for row in range(n):
            if row==column:continue
            factor=aug[row][column]
            aug[row]=[left-factor*right for left,right in zip(aug[row],aug[column])]
    result=[row[-1] for row in aug]
    if not all(finite(value) for value in result):raise ValueError('nonfinite residual fit')
    return result


def fit_residual(pairs,*,cutoff,code_revision,ridge=1.,max_correction_c=6):
    if not finite(ridge) or not 0<ridge<=1000000:raise ValueError('positive bounded ridge regularization required')
    pairs,model=_artifact(pairs,cutoff=cutoff,code_revision=code_revision,max_correction_c=max_correction_c,algorithm='ridge_residual',ridge=ridge)
    if pairs:
        matrix=[feature_vector(pair.forecast) for pair in pairs];weights,support=temperature_weights(pairs);count=support['target_weight_sum'];n=len(FEATURE_NAMES)
        centers=[math.fsum(w*row[j] for w,row in zip(weights,matrix))/count for j in range(n)]
        scales=[math.sqrt(math.fsum(w*(row[j]-centers[j])**2 for w,row in zip(weights,matrix))/count) or 1. for j in range(n)]
        matrix=[[(value-centers[j])/scales[j] for j,value in enumerate(row)] for row in matrix]
        errors=[pair.outcome.value_c-pair.forecast.mean_c for pair in pairs];intercept=math.fsum(w*e for w,e in zip(weights,errors))/count
        gram=[[math.fsum(w*row[i]*row[j] for w,row in zip(weights,matrix))+(ridge if i==j else 0) for j in range(n)] for i in range(n)]
        rhs=[math.fsum(w*row[j]*(error-intercept) for w,row,error in zip(weights,matrix,errors)) for j in range(n)]
        model.update(feature_names=list(FEATURE_NAMES),feature_centers=centers,feature_scales=scales,coefficients=_solve(gram,rhs),intercept_c=intercept)
    return model|{'artifact_sha256':identity(model)}


def validate_artifact(model):
    from weather_temperature_evidence import sensor_epoch_id
    current=isinstance(model,dict) and model.get('schema')==SCHEMA
    if not isinstance(model,dict) or set(model)!=(FIELDS|{'support'} if current else FIELDS) or model['schema'] not in (SCHEMA,'earthship-weathernext-temperature-model/v1') or model['provider']!='weathernext3':
        raise ValueError('closed WeatherNext-only artifact required')
    if current:validate_support(model['support'])
    digest(model['artifact_sha256'])
    if model['artifact_sha256']!=identity({key:value for key,value in model.items() if key!='artifact_sha256'}):raise ValueError('model artifact digest differs')
    if model['algorithm'] not in ('bounded_bias','ridge_residual') or model['qualification']!='SHADOW_ONLY':raise ValueError('known shadow model required')
    if not isinstance(model['code_revision'],str) or not re.fullmatch('[0-9a-f]{40}',model['code_revision']):raise ValueError('immutable model code revision required')
    if not finite(model['intercept_c']) or not finite(model['max_correction_c']) or not 0<model['max_correction_c']<=20:
        raise ValueError('finite bounded correction required')
    count=model['sample_count'];manifest=model['training_manifest']
    if type(count) is not int or not 0<=count<=20000 or not isinstance(manifest,list) or len(manifest)!=count:
        raise ValueError('bounded source manifest required')
    cutoff=instant(model['cutoff'])
    if type(model['target_dates']) is not int or not 0<=model['target_dates']<=count:raise ValueError('bounded unique target-date count required')
    if count:
        digest(model['grid_digest']);sensor_epoch_id(model['sensor_epoch']);zone=ZoneInfo(model['site_timezone'])
        starts=[];seen=set()
        for row in manifest:
            if not isinstance(row,dict) or set(row)!={'pair_sha256','snapshot_sha256','issue_sha256','outcome_sha256','target_at','issued_at'}:
                raise ValueError('closed Google/local source manifest required')
            for key in ('pair_sha256','snapshot_sha256','issue_sha256','outcome_sha256'):digest(row[key])
            at,issued=map(instant,(row['target_at'],row['issued_at']))
            if not issued<at<=cutoff or row['pair_sha256'] in seen:raise ValueError('unique completed training targets required')
            seen.add(row['pair_sha256']);starts.append(at)
        if instant(model['training_start'])!=min(starts) or instant(model['training_end'])!=max(starts) or cutoff-min(starts)>timedelta(days=366):
            raise ValueError('training clocks differ from source manifest')
        if model['target_dates']!=len({at.astimezone(zone).date() for at in starts}):raise ValueError('target-date count differs from sources')
    elif any(model[key] is not None for key in ('grid_digest','sensor_epoch','site_timezone','training_start','training_end')) or model['intercept_c']!=0 or model['target_dates']!=0:
        raise ValueError('empty model must be explicitly untrained')
    if current and (model['support']['forecast_pairs']!=count or model['support']['local_target_dates']!=model['target_dates'] or model['support']['unique_measured_targets']!=(len(set(starts)) if count else 0)):
        raise ValueError('target support differs from original manifest')
    n=len(FEATURE_NAMES) if model['algorithm']=='ridge_residual' and count else 0
    if model['feature_names']!=(list(FEATURE_NAMES) if n else []) or any(not isinstance(model[key],list) or len(model[key])!=n for key in ('feature_centers','feature_scales','coefficients')):
        raise ValueError('frozen preprocessing/features required')
    if any(not finite(value) for key in ('feature_centers','feature_scales','coefficients') for value in model[key]) or any(value<=0 for value in model['feature_scales']):
        raise ValueError('finite positive preprocessing scales required')
    ridge=model['ridge']
    if not finite(ridge) or (model['algorithm']=='bounded_bias' and ridge!=0) or (model['algorithm']=='ridge_residual' and not 0<ridge<=1000000):
        raise ValueError('finite algorithm-specific regularization required')
    return model


class TemperaturePredictor:
    """Validate/copy one immutable artifact once for a batch of targets."""
    def __init__(self,model):
        self._model=json.loads(canonical(validate_artifact(model)))

    def predict(self,target,*,sensor_epoch):
        return _predict(self._model,target,sensor_epoch=sensor_epoch)


def predict(model,target,*,sensor_epoch):
    return TemperaturePredictor(model).predict(target,sensor_epoch=sensor_epoch)


def _predict(model,target,*,sensor_epoch):

    validate_target(target)
    if instant(model['cutoff'])>target.issued_at:raise ValueError('model fitted after original issue')
    count=model['sample_count']
    if count and (model['grid_digest']!=target.grid_digest or model['sensor_epoch']!=sensor_epoch):raise ValueError('inference grid/sensor epoch differs from fitted cohort')
    correction=0.
    if count:
        correction=model['intercept_c']
        if model['algorithm']=='ridge_residual':
            vector=feature_vector(target)
            correction+=sum(coefficient*(value-center)/scale for coefficient,value,center,scale in zip(model['coefficients'],vector,model['feature_centers'],model['feature_scales']))
        correction=max(-model['max_correction_c'],min(model['max_correction_c'],correction))
    value=target.mean_c+correction
    if not finite(value):raise ValueError('nonfinite local prediction refused')
    return dict(provider='weathernext3',status='SHADOW_ONLY' if count else 'UNTRAINED',value_c=value,correction_c=correction,
        model_sha256=model['artifact_sha256'],issue_sha256=target.issue_digest,target_at=target.target_at.isoformat(),automatic_actuation=False)
