"""Installed-shade as-issued observation and source-bound later scoring.

No release qualification, action advice, controller or publication side effects.
The producer must separately prove actual delivery; scoring binds its persisted
publication to this original record. Training data never enter issue-time weather.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from .actions import DENVER
from .dataset import KIVA_COOLDOWN
from .forcing_capture import _canonical, _private_directory
from .forecast_history import SOURCE, MAX_ISSUE_AGE, _window, verify_origin_forecast_receipts
from .graduation_policy import _utc, _sha
from .installed_shade_artifact import (validate_candidate_bundle, _shape, _digest,
    )
from .installed_shade_dynamics import InstalledShadeForcing, STEP
from .operational_origin import _validate_actions
from .origin_capture import _runtime, _temperatures, _number, _object
from .recent_cycles import compare_v2
from .temperature_history import _validate_sensor_receipt

SCHEMA = 'earthship-installed-shade-origin/v1'
OUTPUT_SCHEMA = 'earthship-installed-shade-forecast/v1'
PAIR_SCHEMA = 'earthship-installed-shade-source-scored-pair/v1'
MAX_CAPTURE_BYTES = 1000000
MAX_OUTPUT_BYTES = 16384
VENT_DEFAULT_FROM = datetime(2026, 11, 1, tzinfo=DENVER)
FIELDS = {'schema', 'issued_at', 'inputs_available_at', 'published_at', 'candidate',
    'runtime', 'forecast', 'current', 'origin_temperatures', 'action_snapshot',
    'source_epochs', 'output', 'capture_sha256'}
RUNTIME_PATHS = {'thermal_model/installed_shade_origin.py',
    'thermal_model/installed_shade_dynamics.py', 'thermal_model/installed_shade_artifact.py',
    'thermal_model/forecast_history.py'}


@dataclass(frozen=True)
class PreparedCandidate:
    artifact_json: bytes
    validated_at: datetime


def prepare_candidate(bundle, inputs, *, expected_runtime_revision, assessed_at):
    bundle, inputs = deepcopy(bundle), deepcopy(inputs)
    validate_candidate_bundle(bundle, inputs, expected_runtime_revision=expected_runtime_revision,
                              assessed_at=assessed_at)
    return PreparedCandidate(_canonical(bundle['artifact']), _utc(assessed_at))


def _origin_actions(snapshot, issue):
    if not isinstance(snapshot, dict): raise ValueError('original origin action snapshot required')
    value = deepcopy(snapshot)
    if not isinstance(value.get('actions'), dict): raise ValueError('original action map required')
    value['origin'] = _utc(value.get('origin'))
    for event in [*value.get('actions', {}).values(), value.get('mode')]:
        if event is None: continue
        if not isinstance(event, dict): raise ValueError('original action event required')
        for key in ('effective_at', 'received_at', 'created_at'): event[key] = _utc(event.get(key))
        if not 0 <= _number(event.get('confidence')) <= 1:
            raise ValueError('bounded original action confidence required')
    _validate_actions(value, issue)
    known = value['actions']
    outdoor = known.get('outdoor_shade'); indoor = known.get('indoor_shade'); vent = known.get('vent'); heat = known.get('kiva')
    if outdoor is None or outdoor['state'] not in ('installed', 'present'):
        raise ValueError('origin outside installed-outdoor-shade domain')
    if indoor is None or indoor['state'] not in ('open', 'closed'):
        raise ValueError('origin indoor shade state unavailable')
    if (heat is None or heat['state'] != 'off' or issue-heat['effective_at'] < KIVA_COOLDOWN):
        raise ValueError('origin passive thermal domain unavailable')
    operator_override = (vent is not None and vent['source'] in ('manual_dm', 'nostr_confirmed') and
        vent['effective_at'] >= VENT_DEFAULT_FROM and vent['confidence'] == 1.)
    if issue >= VENT_DEFAULT_FROM and not operator_override:
        vent_value = 0.; vent_provenance = 'operator_default_no_vent'
    else:
        if vent is None or vent['state'] not in ('open', 'closed'):
            raise ValueError('origin vent state unavailable')
        vent_value = float(vent['state'] == 'open'); vent_provenance = vent['source']
    mode = 'unknown' if value['mode'] is None else value['mode']['state']
    if mode not in ('warm', 'spring', 'fall_charge', 'winter', 'unknown'):
        raise ValueError('origin mode state unsupported')
    return dict(indoor_shade_closed=float(indoor['state'] == 'closed'),
        outdoor_shade_present=1., vent_open=vent_value, vent_provenance=vent_provenance,
        mode=mode, action_knowledge='as_of_snapshot_not_outcome_confirmation')


def _forecast_forcing(forecast, issue, available, actions):
    verify_origin_forecast_receipts(forecast)
    fields = {'schema', 'source', 'origin', 'horizon_hours', 'issued_at', 'captured_at', 'rows_sha256', 'rows', 'metric_receipts'}
    if not isinstance(forecast, dict) or set(forecast) != fields or forecast['source'] != SOURCE:
        raise ValueError('original existing-provider forecast required')
    hours = forecast['horizon_hours']; _, targets = _window(issue, hours)
    issued, captured = _utc(forecast['issued_at']), _utc(forecast['captured_at'])
    if (_utc(forecast['origin']) != issue or not issue-MAX_ISSUE_AGE <= issued <= captured <= available <= issue):
        raise ValueError('weather forecast unavailable or stale at origin')
    _sha(forecast['rows_sha256'])
    rows = forecast['rows']
    if not isinstance(rows, list) or len(rows) != len(targets): raise ValueError('original hourly weather bracket incomplete')
    hourly = []
    for target, row in zip(targets, rows):
        if not isinstance(row, dict) or set(row) != {'at', 'tempF', 'radiationWm2', 'windMph', 'weatherCode'} or _utc(row['at']) != target:
            raise ValueError('original hourly weather grid differs')
        outside, radiation = _number(row['tempF']), _number(row['radiationWm2'])
        wind, code = _number(row['windMph']), _number(row['weatherCode'])
        if not -40 <= outside <= 140 or not 0 <= radiation <= 1600 or wind < 0 or not 0 <= code <= 99:
            raise ValueError('original weather outside physical bounds')
        hourly.append((target, outside, radiation))
    result = []; index = 0
    for step in range(1, hours*12+1):
        at = issue+step*STEP
        while index+1 < len(hourly)-1 and hourly[index+1][0] < at: index += 1
        left, right = hourly[index], hourly[index+1]
        fraction = (at-left[0])/(right[0]-left[0])
        if not 0 <= fraction <= 1: raise ValueError('weather interpolation cannot extrapolate')
        result.append(InstalledShadeForcing(at, left[1]+fraction*(right[1]-left[1]),
            left[2]+fraction*(right[2]-left[2]), actions['indoor_shade_closed'],
            actions['outdoor_shade_present'], actions['vent_open']))
    return tuple(result)


def _prediction(record):
    issue, available, published = map(_utc, (record['issued_at'], record['inputs_available_at'], record['published_at']))
    if issue.second or issue.microsecond or issue.minute % 5 or not available <= issue <= published:
        raise ValueError('aligned original issue/publication clocks required')
    runtime = record['runtime']; _runtime(runtime)
    if not RUNTIME_PATHS <= set(runtime['source_manifest']): raise ValueError('installed-shade runtime closure incomplete')
    revision = _digest(runtime)
    model = _shape(record['candidate'], expected_runtime_revision=revision, assessed_at=issue)
    if _utc(record['origin_temperatures']['assessed_at']) > available:
        raise ValueError('initial temperature inputs unavailable at original availability clock')
    if not isinstance(record['current'], dict): raise ValueError('original current state required')
    phases, initial = _temperatures(record['origin_temperatures'], record['current'],
        issued_at=issue, published_at=published, version=2)
    if phases != record['candidate']['sensor_epochs']: raise ValueError('origin sensor phase differs from candidate')
    actions = _origin_actions(record['action_snapshot'], issue)
    forcings = _forecast_forcing(record['forecast'], issue, available, actions)
    result = model.rollout(origin_at=issue, air_f=initial['air'], mass_f=initial['mass'], forcings=forcings)
    # The complete numerical grid is replayed, while the issued payload stays
    # within the existing publication byte budget and exposes exact hour targets.
    trajectory = [dict(at=row.at.isoformat(), air_f=state[0], mass_f=state[1])
                  for index, (row, state) in enumerate(zip(forcings, result.states), 1) if index % 12 == 0]
    output = dict(schema=OUTPUT_SCHEMA, status='shadow', generated_at=issue.isoformat(),
        artifact_sha256=record['candidate']['artifact_sha256'], runtime_sha256=revision,
        horizon_hours=record['forecast']['horizon_hours'],
        initial=dict(air_f=initial['air'], mass_f=initial['mass'], outdoor_f=initial['outdoor']),
        origin_actions=actions, trajectory=trajectory, confidence='unqualified',
        prediction_intervals=None, advice=[], release_authorized=False, automatic_actuation=False)
    if len(_canonical(output)) > MAX_OUTPUT_BYTES: raise ValueError('issued forecast byte budget exceeded')
    return output, phases


def build_issued_capture(candidate, *, issued_at, inputs_available_at, published_at,
                         runtime, forecast, current, origin_temperatures, action_snapshot):
    if not isinstance(candidate, PreparedCandidate) or candidate.validated_at > _utc(issued_at):
        raise ValueError('candidate source verification unavailable at issue')
    record = json.loads(_canonical(dict(schema=SCHEMA, issued_at=_utc(issued_at).isoformat(),
        inputs_available_at=_utc(inputs_available_at).isoformat(), published_at=_utc(published_at).isoformat(),
        candidate=json.loads(candidate.artifact_json), runtime=runtime, forecast=forecast,
        current=current, origin_temperatures=origin_temperatures, action_snapshot=action_snapshot)))
    record['output'], record['source_epochs'] = _prediction(record)
    record['capture_sha256'] = _digest(record)
    return validate_issued_capture(record)


def validate_issued_capture(record):
    if not isinstance(record, dict) or set(record) != FIELDS or record['schema'] != SCHEMA or len(_canonical(record)) > MAX_CAPTURE_BYTES:
        raise ValueError('closed bounded installed-shade original capture required')
    if _digest({k: v for k, v in record.items() if k != 'capture_sha256'}) != _sha(record['capture_sha256']):
        raise ValueError('original installed-shade capture digest differs')
    output, phases = _prediction(record)
    if _canonical(output) != _canonical(record['output']) or phases != record['source_epochs']:
        raise ValueError('issued prediction differs from original source replay')
    return record


def write_issued_capture(directory, record):
    record = deepcopy(record); validate_issued_capture(record)
    root = _private_directory(Path(directory))
    # Capture files are larger than candidate files, so retain the same atomic
    # private writer with this schema's explicit byte bound.
    path = root/(record['capture_sha256']+'.installed-shade-origin-v1.json')
    from .runtime_bundle import _owned_bytes, _write_private, _sync_directory
    from .rollback import _rename_new
    from uuid import uuid4
    raw = _canonical(record)
    if path.exists():
        if _owned_bytes(path, MAX_CAPTURE_BYTES) != raw: raise ValueError('original issued capture differs')
        return path
    temporary = root/('.issued-'+uuid4().hex)
    try:
        _write_private(temporary, raw); _rename_new(temporary, path); _sync_directory(root)
    finally:
        if temporary.exists(): temporary.unlink()
    return path


def read_issued_capture(path):
    from .runtime_bundle import _owned_bytes
    path = Path(path); _private_directory(path.parent)
    def reject(_): raise ValueError('nonfinite original capture JSON')
    try: record = json.loads(_owned_bytes(path, MAX_CAPTURE_BYTES), object_pairs_hook=_object, parse_constant=reject)
    except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError('original capture JSON invalid') from None
    validate_issued_capture(record)
    if path.name != record['capture_sha256']+'.installed-shade-origin-v1.json': raise ValueError('original capture address differs')
    return record


def score_issued_capture(record, *, publication, horizon_hours, outcome, recent_cycle_grid, assessed_at):
    validate_issued_capture(record)
    if type(horizon_hours) is not int or horizon_hours not in (1, 6, 12, 24, 48):
        raise ValueError('supported original scoring horizon required')
    issue = _utc(record['issued_at']); now = _utc(assessed_at); target = issue+timedelta(hours=horizon_hours)
    if (not isinstance(publication, dict) or set(publication) != {'time', 'state'} or
            type(publication['time']) is not int or not isinstance(publication['state'], str) or
            len(publication['state'].encode()) > MAX_OUTPUT_BYTES):
        raise ValueError('bounded original persisted publication required')
    stored = datetime.fromtimestamp(publication['time']/1000, timezone.utc)
    published = _utc(record['published_at'])
    if not issue <= stored <= published < target <= now-timedelta(minutes=5):
        raise ValueError('published forecast/later outcome not mature')
    try: output = json.loads(publication['state'], object_pairs_hook=_object)
    except (ValueError, UnicodeDecodeError): raise ValueError('persisted original publication invalid') from None
    if _canonical(output) != _canonical(record['output']): raise ValueError('persisted publication differs from original issued output')
    points = [p for p in output['trajectory'] if _utc(p['at']) == target]
    if len(points) != 1: raise ValueError('original exact horizon target unavailable')
    if not isinstance(outcome, dict) or set(outcome) != {'target_at', 'receipt'} or _utc(outcome['target_at']) != target:
        raise ValueError('qualified native outcome target differs')
    phase = record['source_epochs']['air']; receipt = outcome['receipt']
    _validate_sensor_receipt(receipt, target, sensor_epoch=phase)
    if not isinstance(recent_cycle_grid, list) or len(recent_cycle_grid) > 64: raise ValueError('bounded original recent-cycle grid required')
    native = {}
    for row in recent_cycle_grid:
        if not isinstance(row, list) or len(row) != 2: raise ValueError('original comparator target/receipt required')
        at = _utc(row[0])
        if at >= issue or at in native: raise ValueError('future or duplicate comparator target')
        value = row[1]
        if value is not None:
            _validate_sensor_receipt(value, at, sensor_epoch=phase)
            value = {**value, **{k: _utc(value[k]) for k in ('receivedAt', 'storedAt', 'validUntil')}}
        native[at] = value
    def read(targets, assessed):
        if assessed != issue: raise ValueError('recent-cycle inputs assessed after original issue')
        return [(at, native.get(at)) for at in targets]
    initial = output['initial']['air_f']
    baseline = compare_v2(issue=issue, target=target, current_f=initial, grid_reader=read, sensor_epoch=phase)
    if baseline['status'] != 'available': raise ValueError('seven original qualified cycles unavailable')
    observed = _number(receipt['temperatureF']); mode = output['origin_actions']['mode']
    regime = {'warm':'warm', 'winter':'winter', 'spring':'shoulder', 'fall_charge':'shoulder'}.get(mode, 'unknown')
    scored = dict(issue_at=issue.isoformat(), target_at=target.isoformat(), horizon_hours=horizon_hours,
        regime=regime, artifact_sha256=record['candidate']['artifact_sha256'], runtime_sha256=_digest(record['runtime']),
        sensor_epochs=dict(record['source_epochs']), model_error_f=points[0]['air_f']-observed,
        persistence_error_f=initial-observed, recent_cycle_error_f=baseline['prediction_f']-observed,
        interval_width_f=None, interval_covered=None)
    return dict(schema=PAIR_SCHEMA, scored_pair=scored, original_capture_sha256=record['capture_sha256'],
        publication_sha256=_digest(publication), outcome_receipt_sha256=_digest(outcome),
        recent_cycle_grid_sha256=_digest(recent_cycle_grid), recent_cycle_evidence_sha256=baseline['evidence_sha256'],
        forecast_source_binding_verified=True, action_response_qualification_claimed=False, release_authorized=False)


# Numeric/v6 is calibrated, v7 is reserved for its main publication capture.
SOURCE_SCHEMA='earthship-installed-shade-origin/v8'
SOURCE_OUTPUT_SCHEMA='earthship-installed-shade-forecast/v5'
SOURCE_PAIR_SCHEMA='earthship-installed-shade-source-scored-pair/v8'
SOURCE_FIELDS=FIELDS|{'native_origin_binding'}


def _replay_source_origin(record):
    from .installed_shade_raw_score_sources import replay_native_origin_binding
    from .replay_budget import check_shared_budget
    return replay_native_origin_binding(record['native_origin_binding'],record['origin_temperatures'],
        issue_at=record['issued_at'],check_budget=check_shared_budget)


def _source_core(record):
    """Internal unchanged numerical view; never an original v1 publication."""
    core={key:deepcopy(record[key]) for key in FIELDS-{'output','source_epochs','capture_sha256'}}
    core['schema']=SCHEMA
    core['output'],core['source_epochs']=_prediction(core)
    core['capture_sha256']=_digest(core)
    return core


def _source_prediction(record):
    from .installed_shade_publication import RAW_RUNTIME_PATHS
    _replay_source_origin(record)
    if not RAW_RUNTIME_PATHS<=set(record['runtime']['source_manifest']):
        raise ValueError('complete original-query runtime closure required')
    core=_source_core(record);output=deepcopy(core['output'])
    output.update(schema=SOURCE_OUTPUT_SCHEMA,native_origin_binding_sha256=_digest(record['native_origin_binding']))
    if len(_canonical(output))>MAX_OUTPUT_BYTES:raise ValueError('query-bound base forecast byte budget exceeded')
    _replay_source_origin(record)
    return output,core['source_epochs']


def build_source_issued_capture(candidate,*,issued_at,inputs_available_at,published_at,
                               runtime,forecast,current,origin_temperatures,action_snapshot,native_source_paths):
    from .installed_shade_raw_score_sources import build_native_origin_binding
    from .replay_budget import check_shared_budget
    if not isinstance(candidate,PreparedCandidate) or candidate.validated_at>_utc(issued_at):
        raise ValueError('candidate source verification unavailable at issue')
    binding=build_native_origin_binding(origin_temperatures,source_paths=native_source_paths,
        issue_at=issued_at,check_budget=check_shared_budget)
    record=json.loads(_canonical(dict(schema=SOURCE_SCHEMA,issued_at=_utc(issued_at).isoformat(),
        inputs_available_at=_utc(inputs_available_at).isoformat(),published_at=_utc(published_at).isoformat(),
        candidate=json.loads(candidate.artifact_json),runtime=runtime,forecast=forecast,current=current,
        origin_temperatures=origin_temperatures,action_snapshot=action_snapshot,native_origin_binding=binding)))
    record['output'],record['source_epochs']=_source_prediction(record);record['capture_sha256']=_digest(record)
    return validate_source_issued_capture(record)


def validate_source_issued_capture(record):
    if (not isinstance(record,dict) or set(record)!=SOURCE_FIELDS or record['schema']!=SOURCE_SCHEMA or
            len(_canonical(record))>MAX_CAPTURE_BYTES or
            _digest({k:v for k,v in record.items() if k!='capture_sha256'})!=_sha(record['capture_sha256'])):
        raise ValueError('closed bounded query-bound base capture required')
    output,phases=_source_prediction(record)
    if _canonical(output)!=_canonical(record['output']) or phases!=record['source_epochs']:
        raise ValueError('query-bound base forecast differs from original replay')
    return record


def write_source_issued_capture(directory,record):
    from .installed_shade_calibration import _persist
    record=deepcopy(record);validate_source_issued_capture(record);root=_private_directory(Path(directory))
    return _persist(root,record,record['capture_sha256'],'.installed-shade-origin-v8.json',
        before_publish=lambda:_replay_source_origin(record))


def read_source_issued_capture(path):
    from .runtime_bundle import _owned_bytes
    path=Path(path);_private_directory(path.parent)
    def reject(_):raise ValueError('nonfinite original query-bound capture JSON')
    try:record=json.loads(_owned_bytes(path,MAX_CAPTURE_BYTES),object_pairs_hook=_object,parse_constant=reject)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('original query-bound capture JSON invalid') from None
    validate_source_issued_capture(record)
    if path.name!=record['capture_sha256']+'.installed-shade-origin-v8.json':raise ValueError('query-bound base capture address differs')
    return record


def score_source_issued_capture(record,*,publication,horizon_hours,outcome,recent_cycle_grid,assessed_at):
    validate_source_issued_capture(record)
    if (not isinstance(publication,dict) or set(publication)!={'time','state'} or
            type(publication['time']) is not int or not isinstance(publication['state'],str) or
            len(publication['state'].encode())>MAX_OUTPUT_BYTES):
        raise ValueError('bounded actual query-bound numeric receipt required')
    try:issued=json.loads(publication['state'],object_pairs_hook=_object)
    except (ValueError,UnicodeDecodeError):raise ValueError('actual query-bound numeric receipt invalid') from None
    if _canonical(issued)!=_canonical(record['output']):raise ValueError('actual numeric receipt differs from original query-bound issue')
    core=_source_core(record)
    result=score_issued_capture(core,publication=dict(time=publication['time'],state=_canonical(core['output']).decode()),
        horizon_hours=horizon_hours,outcome=outcome,recent_cycle_grid=recent_cycle_grid,assessed_at=assessed_at)
    _replay_source_origin(record)
    result.update(schema=SOURCE_PAIR_SCHEMA,original_capture_sha256=record['capture_sha256'],
        publication_sha256=_digest(publication),native_origin_binding_sha256=_digest(record['native_origin_binding']))
    return result
