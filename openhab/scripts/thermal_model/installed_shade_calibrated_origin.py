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
from .installed_shade_calibrated_artifact import _shape, validate_calibrated_candidate, validate_raw_calibrated_candidate
from .installed_shade_calibration import _persist, _read_json
from .installed_shade_fit import HORIZONS
from . import installed_shade_origin as base
from .origin_capture import _object

SCHEMA = 'earthship-installed-shade-origin/v2'
OUTPUT_SCHEMA = 'earthship-installed-shade-forecast/v2'
PAIR_SCHEMA = 'earthship-installed-shade-source-scored-pair/v2'
# Origin/v3 and v5, and their scored pairs, belong to main publication capture.
RAW_SCHEMA = 'earthship-installed-shade-origin/v4'
RAW_OUTPUT_SCHEMA = 'earthship-installed-shade-forecast/v3'
RAW_PAIR_SCHEMA = 'earthship-installed-shade-source-scored-pair/v4'
SOURCE_SCHEMA = 'earthship-installed-shade-origin/v6'
SOURCE_OUTPUT_SCHEMA = 'earthship-installed-shade-forecast/v4'
SOURCE_PAIR_SCHEMA = 'earthship-installed-shade-source-scored-pair/v6'
FIELDS = base.FIELDS
SOURCE_FIELDS = FIELDS | {'native_origin_binding'}
CAPTURE_SCHEMAS = {2:SCHEMA,4:RAW_SCHEMA,6:SOURCE_SCHEMA}
OUTPUT_SCHEMAS = {2:OUTPUT_SCHEMA,4:RAW_OUTPUT_SCHEMA,6:SOURCE_OUTPUT_SCHEMA}
PAIR_SCHEMAS = {2:PAIR_SCHEMA,4:RAW_PAIR_SCHEMA,6:SOURCE_PAIR_SCHEMA}
MAX_CAPTURE_BYTES = base.MAX_CAPTURE_BYTES
MAX_OUTPUT_BYTES = base.MAX_OUTPUT_BYTES


@dataclass(frozen=True)
class PreparedCalibratedCandidate:
    artifact_json: bytes
    validated_at: datetime


@dataclass(frozen=True)
class PreparedRawCalibratedCandidate:
    artifact_json: bytes
    validated_at: datetime


def _check_version(version):
    if type(version) is not int or version not in (2,4,6):
        raise ValueError('explicit calibrated issuance version required')


def _prepare_calibrated_candidate(artifact, *, base_bundle, inputs, calibration,
                                 original_pairs, expected_runtime_revision, assessed_at, _version=2):
    _check_version(_version)
    artifact,base_bundle,inputs,calibration,original_pairs = deepcopy(
        (artifact,base_bundle,inputs,calibration,original_pairs))
    (validate_raw_calibrated_candidate if _version in (4,6) else validate_calibrated_candidate)(artifact,base_bundle=base_bundle,inputs=inputs,calibration=calibration,
        original_pairs=original_pairs,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    return (PreparedRawCalibratedCandidate if _version in (4,6) else PreparedCalibratedCandidate)(_canonical(artifact),_utc(assessed_at))


def _core_view(record):
    value={key:deepcopy(record[key]) for key in base.FIELDS-{'output','source_epochs','capture_sha256'}}
    value.update(schema=base.SCHEMA,candidate=deepcopy(record['candidate']['base_candidate']),
        runtime=deepcopy(record['candidate']['base_runtime']))
    value['output'],value['source_epochs']=base._prediction(value)
    value['capture_sha256']=_digest(value)
    return value


def _prediction(record, *, _version=2):
    _check_version(_version)
    if _version==6:_replay_origin_sources(record)
    issue=_utc(record['issued_at']);artifact=record['candidate'];revision=_digest(record['runtime'])
    _shape(artifact,expected_runtime_revision=revision,assessed_at=issue,_version=3 if _version in (4,6) else 2)
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
    output.update(schema=OUTPUT_SCHEMAS[_version],artifact_sha256=artifact['artifact_sha256'],runtime_sha256=revision,
        prediction_intervals=intervals)
    if _version==6:output['native_origin_binding_sha256']=_digest(record['native_origin_binding'])
    if len(_canonical(output))>MAX_OUTPUT_BYTES:raise ValueError('calibrated issued payload byte budget exceeded')
    if _version==6:_replay_origin_sources(record)
    return output,core['source_epochs']


def _build_calibrated_capture(candidate, *, issued_at, inputs_available_at, published_at,
                             runtime, forecast, current, origin_temperatures, action_snapshot, native_source_paths=None, _version=2):
    _check_version(_version)
    if not isinstance(candidate,PreparedRawCalibratedCandidate if _version in (4,6) else PreparedCalibratedCandidate) or candidate.validated_at>_utc(issued_at):
        raise ValueError('source-verified calibrated candidate unavailable at issue')
    if _version!=6 and native_source_paths is not None:raise ValueError('original query paths require explicit source capture')
    binding=None
    if _version==6:
        from .installed_shade_raw_score_sources import build_native_origin_binding
        from .replay_budget import check_shared_budget
        binding=build_native_origin_binding(origin_temperatures,source_paths=native_source_paths,issue_at=issued_at,check_budget=check_shared_budget)
    record=json.loads(_canonical(dict(schema=CAPTURE_SCHEMAS[_version],issued_at=_utc(issued_at).isoformat(),
        inputs_available_at=_utc(inputs_available_at).isoformat(),published_at=_utc(published_at).isoformat(),
        candidate=json.loads(candidate.artifact_json),runtime=runtime,forecast=forecast,current=current,
        origin_temperatures=origin_temperatures,action_snapshot=action_snapshot)))
    if _version==6:record['native_origin_binding']=binding
    record['output'],record['source_epochs']=_prediction(record,_version=_version);record['capture_sha256']=_digest(record)
    return _validate_calibrated_capture(record,_version=_version)


def _validate_calibrated_capture(record, *, _version=2):
    _check_version(_version)
    if (not isinstance(record,dict) or set(record)!=(SOURCE_FIELDS if _version==6 else FIELDS) or record['schema']!=CAPTURE_SCHEMAS[_version] or
            len(_canonical(record))>MAX_CAPTURE_BYTES or
            _digest({k:v for k,v in record.items() if k!='capture_sha256'})!=record['capture_sha256']):
        raise ValueError('closed bounded calibrated original capture required')
    output,phases=_prediction(record,_version=_version)
    if _canonical(output)!=_canonical(record['output']) or record['source_epochs']!=phases:
        raise ValueError('calibrated issued output differs from original replay')
    return record


def _write_calibrated_capture(directory,record, *, _version=2):
    record=deepcopy(record);_validate_calibrated_capture(record,_version=_version);root=_private_directory(Path(directory))
    return _persist(root,record,record['capture_sha256'],f'.installed-shade-origin-v{_version}.json',
        before_publish=(lambda:_replay_origin_sources(record)) if _version==6 else None)


def _read_calibrated_capture(path, *, _version=2):
    path=Path(path);_private_directory(path.parent);record=_read_json(path);_validate_calibrated_capture(record,_version=_version)
    if path.name!=record['capture_sha256']+f'.installed-shade-origin-v{_version}.json':
        raise ValueError('calibrated original capture address differs')
    return record


def _score_calibrated_capture(record, *, publication, horizon_hours, outcome, recent_cycle_grid, assessed_at, _version=2):
    _validate_calibrated_capture(record,_version=_version)
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
    # below refer exclusively to the actual versioned capture and persisted payload.
    core=_core_view(record)
    result=base.score_issued_capture(core,publication=dict(time=publication['time'],state=_canonical(core['output']).decode()),
        horizon_hours=horizon_hours,outcome=outcome,recent_cycle_grid=recent_cycle_grid,assessed_at=assessed_at)
    band=next(value for value in issued['prediction_intervals'] if value['horizon_hours']==horizon_hours)
    observed=_finite(outcome['receipt']['temperatureF'])
    result['scored_pair'].update(artifact_sha256=record['candidate']['artifact_sha256'],runtime_sha256=_digest(record['runtime']),
        interval_width_f=_finite(band['upper_air_f']-band['lower_air_f']),
        interval_covered=band['lower_air_f']<=observed<=band['upper_air_f'])
    result.update(schema=PAIR_SCHEMAS[_version],original_capture_sha256=record['capture_sha256'],publication_sha256=_digest(publication),
        calibration_sha256=record['candidate']['calibration']['calibration_sha256'])
    if _version==6:
        _replay_origin_sources(record)
        result['native_origin_binding_sha256']=_digest(record['native_origin_binding'])
    return result


def _replay_origin_sources(record):
    from .installed_shade_raw_score_sources import replay_native_origin_binding
    from .replay_budget import check_shared_budget
    return replay_native_origin_binding(record['native_origin_binding'],record['origin_temperatures'],
        issue_at=record['issued_at'],check_budget=check_shared_budget)


def prepare_calibrated_candidate(artifact,**values):
    return _prepare_calibrated_candidate(artifact,**values,_version=2)


def prepare_raw_calibrated_candidate(artifact,**values):
    """Replay the raw candidate proof before granting issuance preparation."""
    return _prepare_calibrated_candidate(artifact,**values,_version=4)


def build_calibrated_capture(candidate,**values):
    return _build_calibrated_capture(candidate,**values,_version=2)


def build_raw_calibrated_capture(candidate,**values):
    return _build_calibrated_capture(candidate,**values,_version=4)


def validate_calibrated_capture(record):
    return _validate_calibrated_capture(record,_version=2)


def validate_raw_calibrated_capture(record):
    return _validate_calibrated_capture(record,_version=4)


def write_calibrated_capture(directory,record):
    return _write_calibrated_capture(directory,record,_version=2)


def write_raw_calibrated_capture(directory,record):
    return _write_calibrated_capture(directory,record,_version=4)


def read_calibrated_capture(path):
    return _read_calibrated_capture(path,_version=2)


def read_raw_calibrated_capture(path):
    return _read_calibrated_capture(path,_version=4)


def score_calibrated_capture(record,**values):
    return _score_calibrated_capture(record,**values,_version=2)


def score_raw_calibrated_capture(record,**values):
    return _score_calibrated_capture(record,**values,_version=4)


def build_source_calibrated_capture(candidate,**values):
    return _build_calibrated_capture(candidate,**values,_version=6)


def validate_source_calibrated_capture(record):
    return _validate_calibrated_capture(record,_version=6)


def write_source_calibrated_capture(directory,record):
    return _write_calibrated_capture(directory,record,_version=6)


def read_source_calibrated_capture(path):
    return _read_calibrated_capture(path,_version=6)


def score_source_calibrated_capture(record,**values):
    return _score_calibrated_capture(record,**values,_version=6)
