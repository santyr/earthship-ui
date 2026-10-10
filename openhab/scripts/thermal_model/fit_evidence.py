"""Artifact-bound measured numerical fit evidence; no release authority.

Raw qualified training sources remain authoritative. This wrapper preserves the
existing artifact schema and derives numerical gates from measured matrices and
actual optimized block-refit coefficients, never a supplied pass flag.
"""
from collections import Counter
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from .artifacts import validate_artifact
from .dynamics import (AIR_NAMES,MASS_NAMES,AIR_BOUNDS,MASS_BOUNDS,
    BLOCK_REFIT_GROUPS,BLOCK_REFIT_MIN_INDEPENDENT_DAYS,BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION,
    NORMALIZED_CONDITION_NUMBER_LIMIT,MultihorizonDynamicsFit,_coefficient_vector,validate_physics)
from .forcing_capture import _canonical,_private_directory
from .origin_capture import _private_file,_object
from .graduation_policy import _utc,_sha
from .schema import DynamicsModel
from .dynamics import SITE_TIMEZONE

SCHEMA='earthship-thermal-fit-evidence/v1'
FIELDS={'schema','artifact_sha256','dynamics_sha256','training_inputs_sha256','code_revision',
    'trained_from','trained_through','created_at','active_parameter_count','coefficient_names',
    'limits','optimizer','conditioning','initializer_block_refit_stability',
    'coefficient_block_refit_stability','block_refits','gates','fit_gates_passed',
    'release_authorized','fit_evidence_sha256'}
SUMMARY_FIELDS={'assessed','independent_days','required_days','refit_count',
                'max_bound_span_fraction','worst_coefficient'}
MATRIX_FIELDS={'stage','label','row_count','column_count','condition_number'}
NAMES=AIR_NAMES+MASS_NAMES


def _digest(value):return sha256(_canonical(value)).hexdigest()


def _limits():
    return dict(normalized_condition_number_limit=float(NORMALIZED_CONDITION_NUMBER_LIMIT),
        block_refit_groups=BLOCK_REFIT_GROUPS,min_independent_days=BLOCK_REFIT_MIN_INDEPENDENT_DAYS,
        max_bound_span_fraction=BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION)


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('finite measured fit number required')
    return float(value)


def _summary(value):
    if not isinstance(value,dict) or set(value)!=SUMMARY_FIELDS:raise ValueError('closed block-refit assessment required')
    if type(value['assessed']) is not bool:raise ValueError('block-refit assessment invalid')
    for name in ('independent_days','required_days','refit_count'):
        if type(value[name]) is not int or value[name]<0:raise ValueError('block-refit support invalid')
    if value['required_days']!=BLOCK_REFIT_MIN_INDEPENDENT_DAYS:raise ValueError('block-refit support threshold changed')
    if value['assessed']:
        if (value['independent_days']<value['required_days'] or value['refit_count']!=BLOCK_REFIT_GROUPS or
                _number(value['max_bound_span_fraction'])<0 or
                value['worst_coefficient'] not in (*NAMES,None) or
                value['max_bound_span_fraction']>0 and value['worst_coefficient'] is None):
            raise ValueError('assessed block-refit evidence inconsistent')
    elif (value['independent_days']>=value['required_days'] or value['refit_count']!=0 or
          value['max_bound_span_fraction'] is not None or value['worst_coefficient'] is not None):
        raise ValueError('insufficient block-refit evidence inconsistent')
    return value


def _blocks(record,artifact):
    summary=_summary(record['coefficient_block_refit_stability'])
    initial=_summary(record['initializer_block_refit_stability'])
    if initial['independent_days']!=summary['independent_days']:raise ValueError('fit day support differs')
    blocks=record['block_refits']
    if not isinstance(blocks,list) or len(blocks)!=summary['refit_count']:raise ValueError('actual block refits missing')
    if not blocks:return summary
    base=tuple(map(float,_coefficient_vector(artifact.dynamics)))
    lower=AIR_BOUNDS[0]+MASS_BOUNDS[0];upper=AIR_BOUNDS[1]+MASS_BOUNDS[1]
    dates=[];worst=0.;worst_name=None
    start=_utc(artifact.trained_from).astimezone(SITE_TIMEZONE).date()
    end=_utc(artifact.trained_through).astimezone(SITE_TIMEZONE).date()
    for group,block in enumerate(blocks):
        if (not isinstance(block,dict) or set(block)!={'group','omitted_days','coefficients'} or
                type(block['group']) is not int or block['group']!=group):raise ValueError('deterministic block identity invalid')
        omitted=block['omitted_days'];coefficients=block['coefficients']
        if (not isinstance(omitted,list) or not omitted or
                not isinstance(coefficients,list) or len(coefficients)!=len(NAMES)):
            raise ValueError('omitted days and actual coefficient vector required')
        for day in omitted:
            if not isinstance(day,str):raise ValueError('canonical omitted day required')
            try:parsed=date.fromisoformat(day)
            except ValueError:raise ValueError('canonical omitted day required') from None
            if parsed.isoformat()!=day or not start<=parsed<=end:raise ValueError('omitted day outside training interval')
        dates.extend(omitted);values=tuple(map(_number,coefficients))
        model=DynamicsModel(version=artifact.dynamics.version,step_minutes=artifact.dynamics.step_minutes,
            air_coefficients=dict(zip(AIR_NAMES,values[:len(AIR_NAMES)])),
            mass_coefficients=dict(zip(MASS_NAMES,values[len(AIR_NAMES):])),
            glazing_observation_coefficients=artifact.dynamics.glazing_observation_coefficients)
        validate_physics(model)
        fractions=[abs(value-origin)/(hi-lo) for value,origin,lo,hi in zip(values,base,lower,upper)]
        index=max(range(len(fractions)),key=fractions.__getitem__)
        if fractions[index]>worst:worst=fractions[index];worst_name=NAMES[index]
    ordered=sorted(set(dates))
    if len(dates)!=len(ordered) or len(ordered)!=summary['independent_days']:
        raise ValueError('independent omitted days differ from assessment')
    if any(block['omitted_days']!=ordered[group::BLOCK_REFIT_GROUPS] for group,block in enumerate(blocks)):
        raise ValueError('omission blocks differ from deterministic day assignment')
    if (not math.isclose(worst,summary['max_bound_span_fraction'],rel_tol=1e-12,abs_tol=1e-14) or
            summary['worst_coefficient']!=worst_name):raise ValueError('stability summary differs from actual refit coefficients')
    return summary


def _gates(record,artifact):
    if _canonical(record['limits'])!=_canonical(_limits()):raise ValueError('numerical fit protection changed')
    diagnostics=artifact.data_manifest['fit_diagnostics']
    expected=dict(origin_counts=diagnostics['multihorizon_origin_counts'],
        initial_objective=diagnostics['multihorizon_initial_objective'],
        final_objective=diagnostics['multihorizon_final_objective'])
    if _canonical(record['optimizer'])!=_canonical(expected):raise ValueError('optimizer evidence differs from artifact')
    summary=_blocks(record,artifact);matrices=record['conditioning']
    if not isinstance(matrices,list) or not 1<=len(matrices)<=128:raise ValueError('bounded measured conditioning required')
    numeric=True
    for value in matrices:
        if not isinstance(value,dict) or set(value)!=MATRIX_FIELDS:raise ValueError('closed measured matrix evidence required')
        if (value['stage'] not in {'initializer','refinement','initializer_block_refit','graduation_block_refit'} or
                value['label'] not in {'fit design','multihorizon sensitivity matrix','multihorizon final sensitivity matrix'} or
                type(value['row_count']) is not int or type(value['column_count']) is not int or
                not 1<=value['column_count']<=len(NAMES) or value['row_count']<value['column_count']):
            raise ValueError('measured matrix dimensions/stage invalid')
        condition=_number(value['condition_number'])
        if condition<1:raise ValueError('normalized matrix condition invalid')
        numeric=numeric and condition<=NORMALIZED_CONDITION_NUMBER_LIMIT
    main=[entry for entry in matrices if entry['stage']=='initializer']
    dimensions=Counter((entry['column_count'],entry['row_count'],entry['label']) for entry in main)
    required=Counter([(3,diagnostics['envelope_identification_pairs'],'fit design'),
        (len(AIR_NAMES)-1,diagnostics['fitted_pairs'],'fit design'),
        (len(MASS_NAMES),diagnostics['fitted_pairs'],'fit design')])
    if artifact.dynamics.glazing_observation_coefficients:
        required[(6,diagnostics['auxiliary_glazing_fitted_rows'],'fit design')]+=1
    if dimensions!=required:raise ValueError('measured initializer dimensions differ from source selection')
    refinement=[entry for entry in matrices if entry['stage']=='refinement']
    expected_rows=2*sum(expected['origin_counts'].values())
    if (len(refinement)!=2 or {entry['label'] for entry in refinement}!={'multihorizon sensitivity matrix','multihorizon final sensitivity matrix'} or
            any(entry['column_count']!=len(NAMES) or entry['row_count']!=expected_rows for entry in refinement)):
        raise ValueError('initial/final optimized sensitivity evidence missing')
    final_blocks=[entry for entry in matrices if entry['stage']=='graduation_block_refit' and entry['label']=='multihorizon final sensitivity matrix']
    if len(final_blocks)!=summary['refit_count'] or any(entry['column_count']!=len(NAMES) for entry in final_blocks):
        raise ValueError('optimized block-refit conditioning missing')
    fitted=diagnostics['fitted_pairs'];days=summary['independent_days']
    if not days<=fitted<=days*288:raise ValueError('fitted pair count incompatible with independent days')
    return dict(numerical_conditioning=numeric,final_conditioning_measured=True,
        independent_day_support=days>=BLOCK_REFIT_MIN_INDEPENDENT_DAYS,
        final_coefficient_stability=summary['assessed'] and summary['max_bound_span_fraction']<=BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION)


def validate_fit_evidence(record,artifact):
    validate_artifact(artifact)
    if not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or record['release_authorized'] is not False:
        raise ValueError('closed versioned numerical fit proof required')
    body={key:value for key,value in record.items() if key!='fit_evidence_sha256'}
    if _digest(body)!=record['fit_evidence_sha256']:raise ValueError('fit proof digest differs')
    for field,expected in dict(artifact_sha256=_digest(asdict(artifact)),dynamics_sha256=_digest(asdict(artifact.dynamics)),
            training_inputs_sha256=artifact.data_manifest['canonical_rows_sha256'],code_revision=artifact.code_revision,
            trained_from=artifact.trained_from,trained_through=artifact.trained_through,created_at=artifact.created_at,
            active_parameter_count=len(NAMES),coefficient_names=[*('air.'+name for name in AIR_NAMES),*('mass.'+name for name in MASS_NAMES)]).items():
        if _canonical(record[field])!=_canonical(expected):raise ValueError('fit proof artifact/training binding differs')
    for name in ('artifact_sha256','dynamics_sha256','training_inputs_sha256','code_revision'):_sha(record[name])
    gates=_gates(record,artifact)
    if _canonical(record['gates'])!=_canonical(gates) or type(record['fit_gates_passed']) is not bool or record['fit_gates_passed']!=all(gates.values()):
        raise ValueError('fit pass claim differs from measured evidence')
    return record


def build_fit_evidence(artifact,fitted):
    if not isinstance(fitted,MultihorizonDynamicsFit) or fitted.inactive_forcing_features or fitted.dynamics!=artifact.dynamics:
        raise ValueError('exact strict final dynamics fit required')
    value=fitted.evidence
    if any(entry is None for entry in (value.conditioning,value.block_refit_stability,
            value.graduation_block_refit_stability,value.graduation_block_refits)):
        raise ValueError('explicit measured graduation fit required')
    body=dict(schema=SCHEMA,artifact_sha256=_digest(asdict(artifact)),dynamics_sha256=_digest(asdict(artifact.dynamics)),
        training_inputs_sha256=artifact.data_manifest['canonical_rows_sha256'],code_revision=artifact.code_revision,
        trained_from=artifact.trained_from,trained_through=artifact.trained_through,created_at=artifact.created_at,
        active_parameter_count=len(NAMES),coefficient_names=[*('air.'+name for name in AIR_NAMES),*('mass.'+name for name in MASS_NAMES)],
        limits=_limits(),optimizer=dict(origin_counts=dict(value.origin_counts),initial_objective=value.initial_objective,final_objective=value.final_objective),
        conditioning=[asdict(entry) for entry in value.conditioning],
        initializer_block_refit_stability=asdict(value.block_refit_stability),
        coefficient_block_refit_stability=asdict(value.graduation_block_refit_stability),
        block_refits=[asdict(entry) for entry in value.graduation_block_refits],release_authorized=False)
    body=json.loads(_canonical(body));body['gates']=_gates(body,artifact)
    body['fit_gates_passed']=all(body['gates'].values());body['fit_evidence_sha256']=_digest(body)
    return validate_fit_evidence(body,artifact)


def read_fit_evidence(path,artifact):
    path=Path(path);_private_directory(path.parent)
    def reject(_):raise ValueError('nonfinite fit proof')
    try:record=json.loads(_private_file(path),object_pairs_hook=_object,parse_constant=reject)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('fit proof JSON invalid') from None
    return validate_fit_evidence(record,artifact)


def write_fit_evidence(directory,record,artifact):
    root=_private_directory(Path(directory));raw=_canonical(validate_fit_evidence(record,artifact))
    if len(raw)>256000:raise ValueError('fit proof exceeds bounded size')
    target=root/(record['artifact_sha256']+'.fit-evidence-v1.json');temporary=root/('.fit-'+uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,target,follow_symlinks=False)
        except FileExistsError:
            if _private_file(target)!=raw:raise ValueError('bound fit proof has different content')
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temporary.unlink(missing_ok=True)
    return target
