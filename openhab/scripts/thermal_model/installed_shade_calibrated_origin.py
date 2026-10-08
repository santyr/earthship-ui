"""Explicit calibrated issued forecasts and later source-bound interval scoring.

These are shadow observations. Qualified production publication is a separate
caller; an artifact/capture hash or calibrated band never authorizes release.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from .forcing_capture import _canonical, _private_directory
from .graduation_policy import _utc, _finite
from .installed_shade_artifact import _digest
from .installed_shade_calibrated_artifact import _shape, validate_calibrated_candidate
from .installed_shade_calibration import _persist, _read_json
from .installed_shade_fit import HORIZONS
from . import installed_shade_origin as base
from .origin_capture import _object

SCHEMA = 'earthship-installed-shade-origin/v2'
OUTPUT_SCHEMA = 'earthship-installed-shade-forecast/v2'
PAIR_SCHEMA = 'earthship-installed-shade-source-scored-pair/v2'
FIELDS = base.FIELDS
MAX_CAPTURE_BYTES = base.MAX_CAPTURE_BYTES
MAX_OUTPUT_BYTES = base.MAX_OUTPUT_BYTES


@dataclass(frozen=True)
class PreparedCalibratedCandidate:
    artifact_json: bytes
    validated_at: datetime


def prepare_calibrated_candidate(artifact, *, base_bundle, inputs, calibration,
                                 original_pairs, expected_runtime_revision, assessed_at):
    artifact,base_bundle,inputs,calibration,original_pairs = deepcopy(
        (artifact,base_bundle,inputs,calibration,original_pairs))
    validate_calibrated_candidate(artifact,base_bundle=base_bundle,inputs=inputs,calibration=calibration,
        original_pairs=original_pairs,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    return PreparedCalibratedCandidate(_canonical(artifact),_utc(assessed_at))


def _core_view(record):
    value={key:deepcopy(record[key]) for key in base.FIELDS-{'output','source_epochs','capture_sha256'}}
    value.update(schema=base.SCHEMA,candidate=deepcopy(record['candidate']['base_candidate']),
        runtime=deepcopy(record['candidate']['base_runtime']))
    value['output'],value['source_epochs']=base._prediction(value)
    value['capture_sha256']=_digest(value)
    return value


def _prediction(record):
    issue=_utc(record['issued_at']);artifact=record['candidate'];revision=_digest(record['runtime'])
    _shape(artifact,expected_runtime_revision=revision,assessed_at=issue)
    if _canonical(record['runtime'])!=_canonical(artifact['runtime']):
        raise ValueError('original calibrated runtime differs from frozen aggregate')
    calibration=artifact['calibration'];bands=calibration['bands']
    if any(value is None for cell in bands.values() for value in [cell['overall'],*cell['regimes'].values()]):
        raise ValueError('independent calibration support incomplete')
    core=_core_view(record);output=deepcopy(core['output'])
    mode=output['origin_actions']['mode'];regime={'warm':'warm','winter':'winter','spring':'shoulder','fall_charge':'shoulder'}.get(mode)
    if regime not in calibration['regimes']:
        raise ValueError('origin regime outside calibrated domain')
    intervals=[]
    for hours in HORIZONS:
        if hours>output['horizon_hours']:raise ValueError('all required calibrated forecast targets unavailable')
        point=output['trajectory'][hours-1];radius=bands[str(hours)]['regimes'][regime]
        lower,upper=_finite(point['air_f']-radius),_finite(point['air_f']+radius)
        _finite(upper-lower)
        intervals.append(dict(at=point['at'],horizon_hours=hours,lower_air_f=lower,upper_air_f=upper,
            nominal_coverage=calibration['method']['nominal_coverage'],regime=regime,
            calibration_sha256=calibration['calibration_sha256']))
    output.update(schema=OUTPUT_SCHEMA,artifact_sha256=artifact['artifact_sha256'],runtime_sha256=revision,
        prediction_intervals=intervals)
    if len(_canonical(output))>MAX_OUTPUT_BYTES:raise ValueError('calibrated issued payload byte budget exceeded')
    return output,core['source_epochs']


def build_calibrated_capture(candidate, *, issued_at, inputs_available_at, published_at,
                             runtime, forecast, current, origin_temperatures, action_snapshot):
    if not isinstance(candidate,PreparedCalibratedCandidate) or candidate.validated_at>_utc(issued_at):
        raise ValueError('source-verified calibrated candidate unavailable at issue')
    record=json.loads(_canonical(dict(schema=SCHEMA,issued_at=_utc(issued_at).isoformat(),
        inputs_available_at=_utc(inputs_available_at).isoformat(),published_at=_utc(published_at).isoformat(),
        candidate=json.loads(candidate.artifact_json),runtime=runtime,forecast=forecast,current=current,
        origin_temperatures=origin_temperatures,action_snapshot=action_snapshot)))
    record['output'],record['source_epochs']=_prediction(record);record['capture_sha256']=_digest(record)
    return validate_calibrated_capture(record)


def validate_calibrated_capture(record):
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or
            len(_canonical(record))>MAX_CAPTURE_BYTES or
            _digest({k:v for k,v in record.items() if k!='capture_sha256'})!=record['capture_sha256']):
        raise ValueError('closed bounded calibrated original capture required')
    output,phases=_prediction(record)
    if _canonical(output)!=_canonical(record['output']) or record['source_epochs']!=phases:
        raise ValueError('calibrated issued output differs from original replay')
    return record


def write_calibrated_capture(directory,record):
    record=deepcopy(record);validate_calibrated_capture(record);root=_private_directory(Path(directory))
    return _persist(root,record,record['capture_sha256'],'.installed-shade-origin-v2.json')


def read_calibrated_capture(path):
    path=Path(path);_private_directory(path.parent);record=_read_json(path);validate_calibrated_capture(record)
    if path.name!=record['capture_sha256']+'.installed-shade-origin-v2.json':
        raise ValueError('calibrated original capture address differs')
    return record


def score_calibrated_capture(record, *, publication, horizon_hours, outcome, recent_cycle_grid, assessed_at):
    validate_calibrated_capture(record)
    if type(horizon_hours) is not int or horizon_hours not in HORIZONS:
        raise ValueError('source-calibrated original scoring horizon required')
    if (not isinstance(publication,dict) or set(publication)!={'time','state'} or
            type(publication['time']) is not int or not isinstance(publication['state'],str) or
            len(publication['state'].encode())>MAX_OUTPUT_BYTES):
        raise ValueError('bounded original persisted calibrated publication required')
    try:issued=json.loads(publication['state'],object_pairs_hook=_object)
    except (ValueError,UnicodeDecodeError):raise ValueError('original calibrated publication JSON invalid') from None
    if _canonical(issued)!=_canonical(record['output']):
        raise ValueError('persisted calibrated publication differs from original issued output')
    # This view reuses the unchanged native/weather/physical/baseline contracts;
    # it is never claimed to be an original v1 publication. Returned bindings
    # below refer exclusively to the actual v2 capture and persisted payload.
    core=_core_view(record)
    result=base.score_issued_capture(core,publication=dict(time=publication['time'],state=_canonical(core['output']).decode()),
        horizon_hours=horizon_hours,outcome=outcome,recent_cycle_grid=recent_cycle_grid,assessed_at=assessed_at)
    band=next(value for value in issued['prediction_intervals'] if value['horizon_hours']==horizon_hours)
    observed=_finite(outcome['receipt']['temperatureF'])
    result['scored_pair'].update(artifact_sha256=record['candidate']['artifact_sha256'],runtime_sha256=_digest(record['runtime']),
        interval_width_f=_finite(band['upper_air_f']-band['lower_air_f']),
        interval_covered=band['lower_air_f']<=observed<=band['upper_air_f'])
    result.update(schema=PAIR_SCHEMA,original_capture_sha256=record['capture_sha256'],publication_sha256=_digest(publication),
        calibration_sha256=record['candidate']['calibration']['calibration_sha256'])
    return result
