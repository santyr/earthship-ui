"""Actual-time production fits on literal historical or recorded input cohorts.

Historical readiness assumptions never replace actual input arrival at this fit.
A new serving descriptor changes only the source availability class; measurement,
grid, timezone and lead domain remain bound to the original training cohort.
"""
from dataclasses import dataclass,asdict,replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from . import probabilistic as k
from .probabilistic_artifacts import numerical_manifest,numerical_environment,_partition,_in_partition

ROOT=Path(__file__).resolve().parents[3]
SCHEMA='earthship-actual-time-production-training-bundle/v1'
CONTEXT={'kind','measurement_quality','grid_sha256','availability_basis','lead_scope_hours','timezone'}
FIELDS={'schema','role','kind','cohort_sha256','training_cohort_sha256','training_context','serving_parent_cohort_sha256','grid_sha256','timezone','lead_scope_hours','availability_basis','training_availability_basis','cutoff','actual_completed_at','ready_at','expires_at','support','models','training_inputs_sha256','population_sha256','policy_sha256','authorization_policy_sha256','numerical_manifest','numerical_environment','kernel_producer_sha256','transfer_rule','retrospective_only','issued','local_coverage_qualified','probability_claim','automatic_actuation'}
TRANSFER='same_measurement_grid_timezone_lead_actual_time_training/v1'


class ProductionBundle(k._Frozen):
    __slots__=()


@dataclass(frozen=True)
class FittedProduction:
    bundle:ProductionBundle
    training_raw:bytes
    def training_dict(self):return json.loads(self.training_raw)


def production_manifest():
    return numerical_manifest()|{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in (
        'openhab/scripts/weather_learning/production_training.py','openhab/scripts/weather_learning/production_model_admission.py',
        'openhab/scripts/production_model_train.py','openhab/scripts/weather_source_files.py',
        'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json','docs/operations/weathernext3-capabilities/deployment-policy.json')}


def _context(value):
    if (not isinstance(value,dict) or set(value)!=CONTEXT or value['kind'] not in k.KINDS or
            not isinstance(value['measurement_quality'],dict) or not value['measurement_quality'] or len(canonical(value))>8192 or
            value['availability_basis'] not in ('historical_assumed_availability','recorded_ingestion_availability') or
            value['lead_scope_hours'] not in ([0,24],[24,72],[72,168],[168,336])):raise ValueError('closed original training context required')
    digest(value['grid_sha256']);ZoneInfo(value['timezone'])
    return json.loads(canonical(value))


def _cohort(context):return identity({k:v for k,v in context.items() if k!='timezone'})


def _domains(context,partition):
    parent=_cohort(context);original=parent
    serving=dict(context,availability_basis='recorded_ingestion_availability');serving_parent=_cohort(serving)
    if partition is not None:
        original=identity(partition);_partition(partition,cohort_sha256=original,lead_scope_hours=context['lead_scope_hours'])
        if partition['parent_cohort_sha256']!=parent:raise ValueError('original training partition context differs')
        serving_pin=identity(dict(partition,parent_cohort_sha256=serving_parent))
    else:serving_pin=serving_parent
    return original,serving_pin,serving_parent


def fit_production(rows,*,family,training_context,cutoff,policy,population_sha256,authorization,authorization_sha256,completed_at=None,partition=None,guard=lambda:None):
    from .production_model_admission import _authorization
    _authorization(authorization,authorization_sha256)
    if authorization.get('historical_retraining_authorized') is not True:raise ValueError('explicit actual-time retraining authorization required')
    ctx=_context(training_context);policy=k._policy(policy);cutoff=utc(cutoff);digest(population_sha256);rows=k._validate(rows)
    if family not in (('temperature_normal','empirical') if ctx['kind']=='temperature' else ('nonnegative','empirical')):raise ValueError('declared production family/target context required')
    original,serving,serving_parent=_domains(ctx,partition)
    if not rows or any((r.forecast.kind,r.forecast.grid_sha256,r.forecast.timezone,r.forecast.availability_basis,k._lead(r.forecast.origin,r.forecast.target_end),r.forecast.cohort_sha256)!=(ctx['kind'],ctx['grid_sha256'],ctx['timezone'],ctx['availability_basis'],ctx['lead_scope_hours'],original) or not _in_partition(partition,r.forecast) for r in rows):
        raise ValueError('one exact original training cohort/context required')
    if completed_at is not None and utc(completed_at)<cutoff:raise ValueError('actual production completion cannot precede cutoff')
    source,environment,kernel=production_manifest(),numerical_environment(),k._source();guard()
    selected=k._eligible(rows,cutoff,False,policy)
    model=k.fit_marginal(rows,family=family,cutoff=cutoff,completed_at=completed_at,policy=policy,ridge=max(policy['optimization']['ridge_candidates']),retrospective=False,guard=guard)
    if model is None:return None
    finished=datetime.now(timezone.utc) if completed_at is None else utc(completed_at);m=model.to_dict()
    if instant(m['actual_completed_at'])>finished:raise ValueError('actual production fit completion differs')
    training=dict(schema='earthship-actual-time-production-training-inputs/v1',population_sha256=population_sha256,cutoff=cutoff.isoformat(),
        training_context=ctx,training_partition=partition,pairs=[asdict(p) for p in selected],fit_pair_sha256s=m['training_pair_sha256s'],
        numerical_manifest=source,numerical_environment=environment,kernel_producer_sha256=kernel,policy_sha256=policy['policy_sha256'],authorization_policy_sha256=authorization_sha256)
    training['training_inputs_sha256']=identity(training)
    body=dict(schema=SCHEMA,role='actual_time_production_fit',kind=ctx['kind'],cohort_sha256=serving,training_cohort_sha256=original,training_context=ctx,
        serving_parent_cohort_sha256=serving_parent,grid_sha256=ctx['grid_sha256'],timezone=ctx['timezone'],lead_scope_hours=ctx['lead_scope_hours'],
        availability_basis='recorded_ingestion_availability',training_availability_basis=ctx['availability_basis'],
        cutoff=cutoff.isoformat(),actual_completed_at=finished.isoformat(),ready_at=finished.isoformat(),expires_at=m['expires_at'],support=m['support'],models={family:m},
        training_inputs_sha256=training['training_inputs_sha256'],population_sha256=population_sha256,policy_sha256=policy['policy_sha256'],authorization_policy_sha256=authorization_sha256,
        numerical_manifest=source,numerical_environment=environment,kernel_producer_sha256=kernel,transfer_rule=TRANSFER,
        retrospective_only=False,issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    if partition is not None:body['training_partition']=partition
    guard()
    if source!=production_manifest() or environment!=numerical_environment() or kernel!=k._source():raise ValueError('production training numerical runtime changed')
    return FittedProduction(k._freeze(ProductionBundle,body,'bundle_sha256'),canonical(training))


def load_production_bundle(value,*,expected_sha256,policy,require_current=True):
    policy=k._policy(policy);digest(expected_sha256)
    if type(require_current) is not bool:raise ValueError('explicit original production load context required')
    if (not isinstance(value,dict) or set(value)!=(FIELDS|{'bundle_sha256'}|({'training_partition'} if 'training_partition' in value else set())) or
            value['bundle_sha256']!=expected_sha256 or expected_sha256!=identity({k:v for k,v in value.items() if k!='bundle_sha256'}) or
            value['schema']!=SCHEMA or value['role']!='actual_time_production_fit' or value['policy_sha256']!=policy['policy_sha256'] or value['transfer_rule']!=TRANSFER or
            any(value[n] is not False for n in ('retrospective_only','issued','local_coverage_qualified','probability_claim','automatic_actuation'))):raise ValueError('unchanged actual-time production bundle required')
    ctx=_context(value['training_context']);original,serving,parent=_domains(ctx,value.get('training_partition'))
    if (value['training_cohort_sha256'],value['cohort_sha256'],value['serving_parent_cohort_sha256'],value['kind'],value['grid_sha256'],value['timezone'],value['lead_scope_hours'],value['training_availability_basis'],value['availability_basis'])!=(original,serving,parent,ctx['kind'],ctx['grid_sha256'],ctx['timezone'],ctx['lead_scope_hours'],ctx['availability_basis'],'recorded_ingestion_availability'):
        raise ValueError('production source/serving context differs')
    for name in ('training_inputs_sha256','population_sha256','authorization_policy_sha256'):digest(value[name])
    if require_current and (value['numerical_manifest']!=production_manifest() or value['numerical_environment']!=numerical_environment() or value['kernel_producer_sha256']!=k._source()):raise ValueError('production numerical source/environment differs')
    cutoff,ready,completed,expiry=map(instant,(value['cutoff'],value['ready_at'],value['actual_completed_at'],value['expires_at']))
    if not cutoff<=ready==completed<expiry<=ready+timedelta(days=policy['temporal']['actual_model_lifetime_days']):raise ValueError('actual production fitting/readiness clocks required')
    if not isinstance(value['models'],dict) or len(value['models'])!=1:raise ValueError('one explicitly selected production family required')
    family,m=next(iter(value['models'].items()))
    if (family not in (('temperature_normal','empirical') if ctx['kind']=='temperature' else ('nonnegative','empirical')) or
            not isinstance(m,dict) or m.get('model_sha256')!=identity({k:v for k,v in m.items() if k!='model_sha256'}) or m.get('schema')!='earthship-local-marginal-model/v1' or m.get('family')!=family or
            m.get('retrospective_only') is not False or m.get('cohort_sha256')!=original or m.get('availability_basis')!=ctx['availability_basis'] or
            any(m.get(k)!=value[k] for k in ('kind','grid_sha256','timezone','lead_scope_hours','cutoff','policy_sha256')) or
            m.get('numerical_producer_sha256')!=value['kernel_producer_sha256'] or
            not instant(m['training_end'])<cutoff<=instant(m['ready_at'])==instant(m['actual_completed_at'])<=completed<expiry==instant(m['expires_at']) or
            any(m.get(k) is not False for k in ('local_coverage_qualified','automatic_actuation'))):raise ValueError('original actually trained production model differs')
    k.validate_marginal_parameters(family=family,parameters=m.get('parameters'),kind=ctx['kind'])
    members=m.get('training_pair_sha256s');support=m.get('support')
    if (not isinstance(members,list) or len(members)>10000 or len(set(members))!=len(members) or m.get('training_data_sha256')!=identity(members) or
            not isinstance(support,dict) or set(support)!={'pairs','targets','local_dates'} or value['support']!=support or
            any(type(v) is not int or v<0 for v in support.values()) or support['pairs']!=len(members) or
            not policy['temporal']['minimum_training_targets']<=support['targets']<=support['pairs'] or
            not policy['temporal']['minimum_training_local_dates']<=support['local_dates']<=support['targets'] or
            not cutoff-timedelta(days=policy['temporal']['maximum_training_days'])<=instant(m['training_start'])<=instant(m['training_end'])<cutoff):
        raise ValueError('original production training membership/support differs')
    for pin in members:digest(pin)
    obj=object.__new__(ProductionBundle);object.__setattr__(obj,'_raw',canonical(value));return obj


def production_frame(bundle,frame):
    body=bundle.to_dict();ctx=body['training_context']
    if (frame.kind,frame.grid_sha256,frame.timezone,k._lead(frame.origin,frame.target_end),frame.availability_basis)!=(ctx['kind'],ctx['grid_sha256'],ctx['timezone'],ctx['lead_scope_hours'],'recorded_ingestion_availability'):return None
    if frame.cohort_sha256 not in {body['cohort_sha256'],body['serving_parent_cohort_sha256']} or not _in_partition(body.get('training_partition'),frame):return None
    return replace(frame,cohort_sha256=body['cohort_sha256'])


def _check_training(bundle,training,policy):
    body=bundle.to_dict();fields={'schema','population_sha256','cutoff','training_context','training_partition','pairs','fit_pair_sha256s','numerical_manifest','numerical_environment','kernel_producer_sha256','policy_sha256','authorization_policy_sha256','training_inputs_sha256'}
    if (not isinstance(training,dict) or set(training)!=fields or training['schema']!='earthship-actual-time-production-training-inputs/v1' or
            training['training_inputs_sha256']!=body['training_inputs_sha256'] or training['training_inputs_sha256']!=identity({k:v for k,v in training.items() if k!='training_inputs_sha256'}) or
            training['training_partition']!=body.get('training_partition') or
            any(training[k]!=body[k] for k in ('population_sha256','cutoff','training_context','numerical_manifest','numerical_environment','kernel_producer_sha256','policy_sha256','authorization_policy_sha256')) or
            not isinstance(training['pairs'],list) or len(training['pairs'])>10000):raise ValueError('literal production training object differs')
    rows=[];ctx=body['training_context'];cutoff=instant(body['cutoff'])
    for raw in training['pairs']:
        args=dict(raw['forecast']);args.pop('input_sha256')
        pair=k.CalibrationPair(forecast=k.ForecastInput(**args),value=raw['value'],outcome_ready_at=raw['outcome_ready_at'],actual_outcome_available_at=raw['actual_outcome_available_at'],receipt_sha256=raw['receipt_sha256'])
        f=pair.forecast
        if (asdict(pair)!=raw or not _in_partition(body.get('training_partition'),f) or
                (f.kind,f.grid_sha256,f.timezone,f.availability_basis,k._lead(f.origin,f.target_end),f.cohort_sha256)!=(ctx['kind'],ctx['grid_sha256'],ctx['timezone'],ctx['availability_basis'],ctx['lead_scope_hours'],body['training_cohort_sha256'])):
            raise ValueError('literal original production training cohort differs')
        rows.append(pair)
    if k._eligible(rows,cutoff,False,policy)!=rows:raise ValueError('actual past-available inputs required at production training cutoff')
    family,m=next(iter(body['models'].items()));used=[p for p in rows if family!='temperature_normal' or p.forecast.width is not None]
    if (m['training_pair_sha256s']!=[p.pair_sha256 for p in used] or training['fit_pair_sha256s']!=m['training_pair_sha256s'] or
            k._support(used)!=m['support'] or m['original_forecast_sha256s']!=sorted({p.forecast.forecast_sha256 for p in used})):
        raise ValueError('literal production fitted membership/support differs')
    return training


def retain_production(state,prepared,*,policy):
    """Retain new fit/training/source originals under the existing shared cap."""
    import gzip,base64
    from .shadow import _directory
    if not isinstance(prepared,FittedProduction):raise ValueError('original prepared production fit required')
    body=prepared.bundle.to_dict();bundle=load_production_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy)
    training=_check_training(bundle,prepared.training_dict(),policy)
    source={name:(ROOT/name).read_text() for name in body['numerical_manifest']}
    if {name:sha256(raw.encode()).hexdigest() for name,raw in source.items()}!=body['numerical_manifest']:raise ValueError('production source changed before original retention')
    encode=lambda raw:base64.b64encode(gzip.compress(raw,compresslevel=3,mtime=0)).decode('ascii')
    value=dict(schema='earthship-retained-production-training-artifact/v1',bundle=body,
        training_original_gzip_base64=encode(canonical(training)),source_originals_gzip_base64=encode(canonical(source)),
        source_encoding='lossless_gzip_base64_utf8_original_sha256',selected=False,automatic_actuation=False)
    value['artifact_sha256']=identity(value);path=state.root/'production-models';_directory(path)
    state._write(path/(value['artifact_sha256']+'.json'),value,immutable=True)
    read_production(state,value['artifact_sha256'],policy=policy)
    return dict(artifact_sha256=value['artifact_sha256'],bundle_sha256=body['bundle_sha256'])


def read_production(state,artifact_sha256,*,policy,require_current=True):
    from .shadow import _read
    from .probabilistic_artifacts import _decode_original
    digest(artifact_sha256);value=_read(state.root/'production-models'/(artifact_sha256+'.json'),16*1024**2)
    if (not isinstance(value,dict) or set(value)!={'schema','bundle','training_original_gzip_base64','source_originals_gzip_base64','source_encoding','selected','automatic_actuation','artifact_sha256'} or
            value['schema']!='earthship-retained-production-training-artifact/v1' or value['artifact_sha256']!=artifact_sha256 or
            identity({k:v for k,v in value.items() if k!='artifact_sha256'})!=artifact_sha256 or
            value['source_encoding']!='lossless_gzip_base64_utf8_original_sha256' or value['selected'] is not False or value['automatic_actuation'] is not False):
        raise ValueError('unchanged retained production training artifact required')
    body=value['bundle'];bundle=load_production_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy,require_current=require_current)
    training=_decode_original(value['training_original_gzip_base64'],maximum=64*1024**2);_check_training(bundle,training,policy)
    source=_decode_original(value['source_originals_gzip_base64'],maximum=16*1024**2)
    if not isinstance(source,dict) or {name:sha256(raw.encode()).hexdigest() for name,raw in source.items()}!=body['numerical_manifest']:
        raise ValueError('literal original production numerical source bytes differ')
    return bundle
