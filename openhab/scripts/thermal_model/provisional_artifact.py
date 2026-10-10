"""Frozen provisional model with original input and runtime pins, never graduated."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import math
from uuid import UUID
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .runtime_bundle import _owned_bytes
from .policy_registration import _read_private
from .installed_shade_artifact import _persist
from .installed_shade_dynamics import InstalledShadeDynamics

SCHEMA='earthship-provisional-thermal-candidate/v1'
FIELDS={'schema','created_at','runtime','runtime_sha256','snapshot_path','snapshot_file_sha256','fit','artifact_sha256'}
FIT_FIELDS={'mode','confidence','coefficients','initial_coefficients','initial_objective','final_objective','regularization_strength',
 'conditioning_rank','normalized_condition_number','iterations','endpoint_count','fit_executed','stability_assessed','graduated',
 'prediction_intervals','automatic_actuation','source_snapshot_sha256','sensor_epochs','training_start','training_end','horizon_support','independent_origin_dates'}


def candidate_digest(value):return sha256(_canonical({k:v for k,v in value.items() if k!='artifact_sha256'})).hexdigest()


def source_digest(path):
    return sha256(_owned_bytes(Path(path),16*1024*1024)).hexdigest()


def build_candidate(fit,*,runtime,snapshot_path,created_at):
    value=dict(schema=SCHEMA,created_at=_utc(created_at).isoformat(),runtime=deepcopy(runtime),runtime_sha256=sha256(_canonical(runtime)).hexdigest(),
        snapshot_path=str(snapshot_path),snapshot_file_sha256=source_digest(snapshot_path),fit=deepcopy(fit))
    value['artifact_sha256']=candidate_digest(value)
    return validate_candidate(value,assessed_at=created_at,runtime=runtime)


def validate_candidate(value,*,assessed_at,runtime=None):
    try:
        if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:raise ValueError('closed provisional candidate required')
        fit=value['fit']
        if not isinstance(fit,dict) or set(fit)!=FIT_FIELDS:raise ValueError('closed provisional learning evidence required')
        if (fit['mode']!='provisional' or fit['confidence']!='low' or fit['fit_executed'] is not True or
            any(fit[k] is not False for k in ('stability_assessed','graduated','automatic_actuation')) or fit['prediction_intervals'] is not None):
            raise ValueError('provisional evidence cannot claim graduation or control')
        for key in ('coefficients','initial_coefficients'):
            if not isinstance(fit[key],list):raise ValueError('explicit physical coefficient vector required')
            InstalledShadeDynamics(tuple(fit[key]))
        for key in ('initial_objective','final_objective','regularization_strength'):
            if type(fit[key]) not in (int,float) or not math.isfinite(fit[key]) or fit[key]<0:raise ValueError('finite fit evidence required')
        if fit['regularization_strength']!=1 or fit['final_objective']>fit['initial_objective']+1e-6:raise ValueError('invalid regularized improvement')
        if type(fit['conditioning_rank']) is not int or not 0<=fit['conditioning_rank']<=10:raise ValueError('bounded rank diagnostic required')
        condition=fit['normalized_condition_number']
        if fit['conditioning_rank']<10:
            if condition is not None:raise ValueError('rank-deficient condition must be unavailable')
        elif type(condition) not in (int,float) or not math.isfinite(condition) or condition<1:raise ValueError('finite condition diagnostic required')
        for key,maximum in (('iterations',300),('endpoint_count',256),('independent_origin_dates',256)):
            if type(fit[key]) is not int or not 0<=fit[key]<=maximum:raise ValueError('bounded fit support required')
        if fit['endpoint_count']<1 or not 1<=fit['independent_origin_dates']<=fit['endpoint_count']:raise ValueError('real endpoint support required')
        counts=fit['horizon_support']
        if (not isinstance(counts,dict) or set(counts)!={'1','6','12','24'} or
            any(type(x) is not int or not 0<=x<=64 for x in counts.values()) or sum(counts.values())!=fit['endpoint_count']):raise ValueError('closed horizon support required')
        phases=fit['sensor_epochs']
        if not isinstance(phases,dict) or set(phases)!={'air','mass','outdoor'}:raise ValueError('complete native phases required')
        for phase in phases.values():
            parsed=UUID(phase)
            if str(parsed)!=phase or parsed.int==0:raise ValueError('canonical nonzero native phases required')
        start,end,created,assessed=map(_utc,(fit['training_start'],fit['training_end'],value['created_at'],assessed_at))
        if not start<end<=created<=assessed:raise ValueError('original frozen training chronology required')
        for key in ('runtime_sha256','snapshot_file_sha256','artifact_sha256'):_sha(value[key])
        _sha(fit['source_snapshot_sha256'])
        if (not isinstance(value['runtime'],dict) or sha256(_canonical(value['runtime'])).hexdigest()!=value['runtime_sha256'] or
            runtime is not None and _canonical(runtime)!=_canonical(value['runtime'])):raise ValueError('original runtime differs')
        path=Path(value['snapshot_path'])
        if not path.is_absolute() or path.resolve()!=path or source_digest(path)!=value['snapshot_file_sha256']:raise ValueError('original training source changed')
        if candidate_digest(value)!=value['artifact_sha256']:raise ValueError('original provisional artifact differs')
    except (TypeError,KeyError,OverflowError,OSError):raise ValueError('invalid provisional artifact') from None
    return deepcopy(value)


def write_candidate(directory,value,*,assessed_at):
    value=validate_candidate(value,assessed_at=assessed_at)
    return _persist(_private_directory(Path(directory)),value,value['artifact_sha256'],'.provisional-candidate-v1.json')


def read_candidate(path,*,assessed_at,runtime=None):
    return validate_candidate(_read_private(Path(path)),assessed_at=assessed_at,runtime=runtime)
