"""Actual-time candidate bundles with original inputs and preprocessing identity.

These are explicit unselected shadow products. Historical counterfactual fits
cannot be relabeled as actually completed candidates. A caller must retain the
original training input object before acknowledging a bundle or issuing it.
"""
from dataclasses import dataclass,asdict,replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import json
from .contracts import canonical,digest,identity,instant,finite
from .evidence import utc
from . import probabilistic as k

NUMERICAL_FILES=tuple('openhab/scripts/weather_learning/'+name+'.py' for name in (
    'probabilistic','probabilistic_artifacts','probabilistic_issue','probabilistic_population','probabilistic_retained','contracts','evidence','config','normalize',
    'weathernext_ee','historical','features','pv_training_sources','historical_pairs','historical_serving',
    'atmospheric_retained','atmospheric_dataset','weather_response','weights'))
ROOT=Path(__file__).resolve().parents[3]


class CandidateBundle(k._Frozen):
    __slots__=()


@dataclass(frozen=True)
class FittedCandidates:
    bundle:CandidateBundle
    training_raw:bytes
    def training_dict(self):return json.loads(self.training_raw)


def numerical_manifest():return {name:sha256((ROOT/name).read_bytes()).hexdigest() for name in NUMERICAL_FILES}


def numerical_environment():
    import sys,numpy,scipy,numpy.linalg._umath_linalg,numpy._core._multiarray_umath,scipy.optimize._lbfgsb,scipy.special._ufuncs
    paths=[Path(sys.executable).resolve(),Path(numpy.linalg._umath_linalg.__file__),Path(numpy._core._multiarray_umath.__file__),Path(scipy.optimize._lbfgsb.__file__),Path(scipy.special._ufuncs.__file__)]
    return dict(python=sys.version,numpy=numpy.__version__,scipy=scipy.__version__,binary_sha256s={path.name:sha256(path.read_bytes()).hexdigest() for path in paths})


def _families(kind):return ('empirical','temperature_normal','adaptive') if kind=='temperature' else ('empirical','nonnegative')


def _partition(value,*,cohort_sha256,lead_scope_hours):
    if value is None:return None
    fields={'method','parent_cohort_sha256','lower_exclusive_hours','upper_inclusive_hours'}
    if (not isinstance(value,dict) or set(value)!=fields or value['method']!='contiguous_whole_native_leads_greedy_capacity/v1' or
            identity(value)!=cohort_sha256 or not all(finite(value[n]) for n in ('lower_exclusive_hours','upper_inclusive_hours'))):
        raise ValueError('original contiguous lead partition and cohort required')
    digest(value['parent_cohort_sha256']);low,high=value['lower_exclusive_hours'],value['upper_inclusive_hours']
    if not lead_scope_hours[0]<=low<high<=lead_scope_hours[1]:raise ValueError('partition range outside original broad lead scope')
    return dict(value)


def _in_partition(partition,frame):
    lead=(instant(frame.target_end)-instant(frame.origin)).total_seconds()/3600
    return partition is None or partition['lower_exclusive_hours']<lead<=partition['upper_inclusive_hours']


def candidate_frame(bundle,frame):
    """Map only a declared raw parent and lead range into its fitted cohort."""
    body=bundle.to_dict();partition=_partition(body.get('partition'),cohort_sha256=body['cohort_sha256'],lead_scope_hours=body['lead_scope_hours'])
    parents={body['cohort_sha256']} if partition is None else {body['cohort_sha256'],partition['parent_cohort_sha256']}
    if (frame.cohort_sha256 not in parents or not _in_partition(partition,frame) or
            (frame.kind,frame.grid_sha256,frame.timezone,k._lead(frame.origin,frame.target_end),frame.availability_basis)!=(body['kind'],body['grid_sha256'],body['timezone'],body['lead_scope_hours'],body['availability_basis'])):return None
    return replace(frame,cohort_sha256=body['cohort_sha256'])


def fit_candidates(rows,*,cutoff,policy,population_sha256,completed_at=None,partition=None,guard=lambda:None):
    """One coherent recorded-origin cohort, with real label/fit availability.

    Cold hyperparameters are fixed by the pre-outcome protocol. A historical
    score winner never chooses a live parameter, artifact or serving selector.
    """
    policy=k._policy(policy);cutoff=utc(cutoff);digest(population_sha256);rows=k._validate(rows)
    if not rows or len({k._cohort(r.forecast) for r in rows})!=1 or any(r.forecast.availability_basis!='recorded_ingestion_availability' for r in rows):
        raise ValueError('one recorded prospective candidate training cohort required')
    source=numerical_manifest();environment=numerical_environment();kernel=k._source();selected=k._eligible(rows,cutoff,False,policy);f=rows[0].forecast
    partition=_partition(partition,cohort_sha256=f.cohort_sha256,lead_scope_hours=k._lead(f.origin,f.target_end))
    if any(not _in_partition(partition,r.forecast) for r in rows):raise ValueError('training forecast outside declared partition range')
    training=dict(schema='earthship-marginal-candidate-training-inputs/v1',population_sha256=population_sha256,
        cutoff=cutoff.isoformat(),pairs=[asdict(p) for p in selected],numerical_manifest=source,numerical_environment=environment,kernel_producer_sha256=kernel,policy_sha256=policy['policy_sha256'])
    if partition is not None:training['partition']=partition
    training['training_inputs_sha256']=identity(training);models={};selection={}
    for family in _families(f.kind):
        guard();parameter=max(policy['adaptive']['half_life_candidates_hours']) if family=='adaptive' else max(policy['optimization']['ridge_candidates']);selection[family]=parameter
        if family=='adaptive':model=k.fit_adaptive(rows,cutoff=cutoff,completed_at=completed_at,half_life_hours=parameter,policy=policy,retrospective=False)
        else:model=k.fit_marginal(rows,family=family,cutoff=cutoff,completed_at=completed_at,ridge=parameter,policy=policy,retrospective=False,guard=guard)
        models[family]=None if model is None else model.to_dict()
    completed=datetime.now(timezone.utc) if completed_at is None else utc(completed_at)
    if completed<cutoff or any(v is not None and instant(v['actual_completed_at'])>completed for v in models.values()):raise ValueError('actual candidate bundle completion clock required')
    guard()
    if source!=numerical_manifest() or environment!=numerical_environment() or kernel!=k._source():raise ValueError('candidate numerical producer changed while fitting')
    body=dict(schema='earthship-local-marginal-candidate-bundle/v1',role='unselected_shadow_candidates',kind=f.kind,
        cohort_sha256=f.cohort_sha256,grid_sha256=f.grid_sha256,timezone=f.timezone,lead_scope_hours=k._lead(f.origin,f.target_end),availability_basis=f.availability_basis,
        cutoff=cutoff.isoformat(),actual_completed_at=completed.isoformat(),ready_at=completed.isoformat(),
        expires_at=min((v['expires_at'] for v in models.values() if v is not None),default=(completed+timedelta(days=14)).isoformat()),
        support=k._support(selected),models=models,selection=selection,selection_basis='predeclared_cold_parameters_before_any_prospective_outcomes',
        training_inputs_sha256=training['training_inputs_sha256'],population_sha256=population_sha256,policy_sha256=policy['policy_sha256'],
        numerical_manifest=source,numerical_environment=environment,kernel_producer_sha256=kernel,retrospective_only=False,issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    if partition is not None:body['partition']=partition
    bundle=k._freeze(CandidateBundle,body,'bundle_sha256')
    return FittedCandidates(bundle,canonical(training))


def load_candidate_bundle(value,*,expected_sha256,policy,require_current=True):
    policy=k._policy(policy);digest(expected_sha256)
    if type(require_current) is not bool:raise ValueError('explicit original candidate load context required')
    if (not isinstance(value,dict) or value.get('bundle_sha256')!=expected_sha256 or expected_sha256!=identity({n:v for n,v in value.items() if n!='bundle_sha256'}) or
            value.get('schema')!='earthship-local-marginal-candidate-bundle/v1' or value.get('role')!='unselected_shadow_candidates' or
            value.get('policy_sha256')!=policy['policy_sha256'] or value.get('kind') not in k.KINDS or value.get('availability_basis')!='recorded_ingestion_availability' or
            any(value.get(n) is not False for n in ('retrospective_only','issued','local_coverage_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('unchanged original prospective candidate bundle required')
    if require_current and (value.get('numerical_manifest')!=numerical_manifest() or value.get('numerical_environment')!=numerical_environment() or value.get('kernel_producer_sha256')!=k._source()):
        raise ValueError('candidate numerical preprocessing runtime differs')
    _partition(value.get('partition'),cohort_sha256=value['cohort_sha256'],lead_scope_hours=value['lead_scope_hours'])
    if set(value.get('models',{}))!=set(_families(value['kind'])):raise ValueError('declared original candidate families required')
    cutoff,ready,completed,expiry=map(instant,(value['cutoff'],value['ready_at'],value['actual_completed_at'],value['expires_at']))
    if not cutoff<=ready==completed<expiry<=completed+timedelta(days=14):raise ValueError('actual candidate completion and original expiry required')
    for family,model in value['models'].items():
        if model is None:continue
        if (model.get('model_sha256')!=identity({n:v for n,v in model.items() if n!='model_sha256'}) or model.get('schema')!='earthship-local-marginal-model/v1' or
                model.get('family')!=family or model.get('retrospective_only') is not False or model.get('availability_basis')!='recorded_ingestion_availability' or
                any(model.get(n)!=value[n] for n in ('kind','cohort_sha256','grid_sha256','timezone','lead_scope_hours','policy_sha256','cutoff')) or
                not instant(model['ready_at'])==instant(model['actual_completed_at'])<=completed or not instant(model['training_end'])<cutoff or
                model.get('numerical_producer_sha256')!=value['kernel_producer_sha256'] or any(model.get(n) is not False for n in ('local_coverage_qualified','automatic_actuation'))):
            raise ValueError('original actually fitted candidate model differs from bundle')
        parameters=model.get('parameters');count=2 if family=='adaptive' else 5 if family=='empirical' else 3
        if not isinstance(parameters,list) or len(parameters)!=count or any(not finite(v) for v in parameters):raise ValueError('finite original candidate parameters required')
    obj=object.__new__(CandidateBundle);object.__setattr__(obj,'_raw',canonical(value));return obj


def predict_candidates(bundle,frame,*,policy):
    if not isinstance(bundle,CandidateBundle) or not isinstance(frame,k.ForecastInput):raise ValueError('original candidate bundle and forecast-only input required')
    body=bundle.to_dict();load_candidate_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy)
    mapped=candidate_frame(bundle,frame)
    families=_families(body['kind']);local={family:None for family in families if family!='adaptive'};adaptive=None;reason=None
    if instant(frame.origin)<instant(body['ready_at']):reason='candidate_not_ready'
    elif instant(frame.origin)>=instant(body['expires_at']):reason='candidate_expired'
    elif mapped is None:reason='candidate_cohort_changed'
    else:
        frame=mapped
        for family,model in body['models'].items():
            restored=None
            if model is not None:
                restored=object.__new__(k.CalibrationModel);object.__setattr__(restored,'_raw',canonical(model))
            if family=='adaptive':adaptive=k.adaptive_point(restored,frame,policy=policy)
            else:
                prediction=k.predict_marginal(restored,frame,policy=policy);local[family]=None if prediction is None else prediction.to_dict()
        if not any(v is not None for v in local.values()) and not (adaptive and adaptive['candidate_used']):reason='past_support_or_fit_unavailable'
    if adaptive is None and frame.kind=='temperature':adaptive=k.adaptive_point(None,frame,policy=policy)
    return dict(status='raw_fallback' if reason else 'read_only_shadow_candidates',reason=reason,
        bundle_sha256=body['bundle_sha256'],raw=dict(mean=frame.baseline,p10=frame.p10,p50=frame.p50,p90=frame.p90),
        marginals=local,adaptive=adaptive,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)


def _decode_original(encoded,*,maximum):
    import base64,gzip,io
    if not isinstance(encoded,str) or len(encoded)>16*1024**2:raise ValueError('bounded original candidate compression required')
    try:
        compressed=base64.b64decode(encoded,validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum:raise ValueError('bounded expanded original candidate required')
        return json.loads(raw)
    except (ValueError,OSError,EOFError) as error:raise ValueError('original compressed candidate object differs') from error


def _check_training(bundle,training):
    body=bundle.to_dict();fields={'schema','population_sha256','cutoff','pairs','numerical_manifest','numerical_environment','kernel_producer_sha256','policy_sha256','training_inputs_sha256'}
    if 'partition' in body:fields.add('partition')
    partition=_partition(body.get('partition'),cohort_sha256=body['cohort_sha256'],lead_scope_hours=body['lead_scope_hours'])
    if (not isinstance(training,dict) or set(training)!=fields or training.get('partition')!=partition or training['schema']!='earthship-marginal-candidate-training-inputs/v1' or
            training['training_inputs_sha256']!=body['training_inputs_sha256'] or training['training_inputs_sha256']!=identity({n:v for n,v in training.items() if n!='training_inputs_sha256'}) or
            any(training[n]!=body[n] for n in ('population_sha256','cutoff','numerical_manifest','numerical_environment','kernel_producer_sha256','policy_sha256')) or
            not isinstance(training['pairs'],list) or len(training['pairs'])>10000):raise ValueError('original candidate training object differs')
    rows=[];index={}
    for raw in training['pairs']:
        args=dict(raw['forecast']);args.pop('input_sha256');pair=k.CalibrationPair(forecast=k.ForecastInput(**args),value=raw['value'],outcome_ready_at=raw['outcome_ready_at'],actual_outcome_available_at=raw['actual_outcome_available_at'],receipt_sha256=raw['receipt_sha256'])
        f=pair.forecast;cutoff=instant(body['cutoff'])
        if (not _in_partition(partition,f) or asdict(pair)!=raw or f.availability_basis!='recorded_ingestion_availability' or
                (f.kind,f.cohort_sha256,f.grid_sha256,f.timezone,k._lead(f.origin,f.target_end))!=(body['kind'],body['cohort_sha256'],body['grid_sha256'],body['timezone'],body['lead_scope_hours']) or
                not cutoff-timedelta(days=28)<=instant(f.target_end)<cutoff or instant(pair.actual_outcome_available_at)>=cutoff or instant(f.actual_source_available_at)>=cutoff):
            raise ValueError('actual past-available original candidate training required')
        rows.append(pair);index[pair.pair_sha256]=pair
    k._validate(rows)
    if k._support(rows)!=body['support']:raise ValueError('original candidate training support differs')
    for family,model in body['models'].items():
        if model is None:continue
        members=model['training_pair_sha256s']
        if (not isinstance(members,list) or len(members)!=len(set(members)) or any(p not in index for p in members) or identity(members)!=model['training_data_sha256']):
            raise ValueError('original candidate training membership differs')
        subset=[index[p] for p in members]
        if k._support(subset)!=model['support'] or (family=='temperature_normal' and any(p.forecast.width is None for p in subset)):
            raise ValueError('original candidate fitted training support differs')
    return training


def retain_candidates(state,prepared,*,policy):
    """Retain source and training literals; no current/selected model is installed."""
    import gzip,base64
    from .shadow import _directory
    if not isinstance(prepared,FittedCandidates):raise ValueError('original prepared candidate bundle required')
    body=prepared.bundle.to_dict();bundle=load_candidate_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy);training=_check_training(bundle,prepared.training_dict())
    source={name:(ROOT/name).read_text() for name in body['numerical_manifest']}
    if {name:sha256(raw.encode()).hexdigest() for name,raw in source.items()}!=body['numerical_manifest']:raise ValueError('original candidate source changed before retention')
    encode=lambda raw:base64.b64encode(gzip.compress(raw,compresslevel=3,mtime=0)).decode('ascii')
    value=dict(schema='earthship-retained-marginal-candidate-artifact/v1',bundle=body,
        training_original_gzip_base64=encode(canonical(training)),source_originals_gzip_base64=encode(canonical(source)),
        source_encoding='lossless_gzip_base64_utf8_original_sha256',selected=False,automatic_actuation=False)
    value['artifact_sha256']=identity(value);path=state.root/'marginal-models';_directory(path)
    state._write(path/(value['artifact_sha256']+'.json'),value,immutable=True)
    read_candidates(state,value['artifact_sha256'],policy=policy)
    return dict(artifact_sha256=value['artifact_sha256'],bundle_sha256=body['bundle_sha256'])


def read_candidates(state,artifact_sha256,*,policy,require_current=True):
    from .shadow import _read
    digest(artifact_sha256);value=_read(state.root/'marginal-models'/(artifact_sha256+'.json'),16*1024**2)
    if (not isinstance(value,dict) or set(value)!={'schema','bundle','training_original_gzip_base64','source_originals_gzip_base64','source_encoding','selected','automatic_actuation','artifact_sha256'} or
            value['schema']!='earthship-retained-marginal-candidate-artifact/v1' or value['artifact_sha256']!=artifact_sha256 or
            identity({n:v for n,v in value.items() if n!='artifact_sha256'})!=artifact_sha256 or value['source_encoding']!='lossless_gzip_base64_utf8_original_sha256' or value['selected'] is not False or value['automatic_actuation'] is not False):raise ValueError('unchanged original retained candidate artifact required')
    body=value['bundle'];bundle=load_candidate_bundle(body,expected_sha256=body['bundle_sha256'],policy=policy,require_current=require_current)
    training=_decode_original(value['training_original_gzip_base64'],maximum=64*1024**2);_check_training(bundle,training)
    source=_decode_original(value['source_originals_gzip_base64'],maximum=16*1024**2)
    if not isinstance(source,dict) or {name:sha256(raw.encode()).hexdigest() for name,raw in source.items()}!=body['numerical_manifest']:
        raise ValueError('literal original candidate source bytes differ')
    return bundle
