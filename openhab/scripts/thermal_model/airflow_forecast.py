"""As-of split-airflow shadow scenarios with exact-input replay, no publisher.

Observed origin states are explicitly HELD assumptions, not future action
confirmations. This API does not update OpenHAB, send advice or enable control.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import math
import re

from .airflow import AirflowSeed, simulate_airflow
from .airflow_artifact import (MASS_INITIALIZATION, artifact_digest, canonical,
                               utc, validate_artifact)
from .airflow_training import forcing_features
from .dataset import CONFIRMED_SOURCES, KIVA_COOLDOWN, STEP
from .forecast_history import MAX_ISSUE_AGE, SOURCE, _window
from .operational_origin import assemble_origin, _validate_actions
from .temperature_history import _validate_receipt

SCHEMA = 'earthship-split-airflow-forecast/v1'
CAPTURE_SCHEMA = 'earthship-split-airflow-forecast-capture/v1'


def _states(actions, origin):
    _validate_actions(actions, origin)
    if actions.get('vocabulary_version') != 2:
        raise ValueError('distinct v2 origin actions required')
    fields = {'window': ('window_open', {'closed': 0., 'open': 1.}),
              'skylight': ('skylight_open', {'closed': 0., 'open': 1.}),
              'indoor_shade': ('indoor_shade_closed', {'open': 0., 'closed': 1.}),
              'outdoor_shade': ('outdoor_shade_present', {'absent': 0., 'removed': 0., 'present': 1., 'installed': 1.})}
    states = {}
    for name, (field, vocabulary) in fields.items():
        event = actions['actions'].get(name)
        if (event is None or event['source'] not in CONFIRMED_SOURCES | {'photosensor'}
                or type(event['confidence']) not in (int, float) or not math.isfinite(event['confidence'])
                or not 0 < event['confidence'] <= 1 or event['state'] not in vocabulary):
            raise ValueError('origin action unknown or unqualified: ' + name)
        states[field] = vocabulary[event['state']]
    kiva = actions['actions'].get('kiva')
    if (kiva is None or kiva['state'] != 'off' or kiva['source'] not in CONFIRMED_SOURCES
            or type(kiva['confidence']) not in (int, float) or not math.isfinite(kiva['confidence'])
            or not 0 < kiva['confidence'] <= 1):
        raise ValueError('passive forecast requires qualified Kiva-off origin state')
    # Observe the same passive cooldown used by dataset construction.
    if origin - kiva['effective_at'] < KIVA_COOLDOWN:
        raise ValueError('Kiva-off cooldown is incomplete')
    return states


def _hourly(forcing, origin, horizon_hours):
    _, times = _window(origin, horizon_hours)
    if (not isinstance(forcing, dict) or set(forcing) != {'source', 'origin', 'horizon_hours',
            'issued_at', 'captured_at', 'rows_sha256', 'rows'}
            or forcing.get('source') != SOURCE or utc(forcing['origin']) != origin
            or forcing.get('horizon_hours') != horizon_hours
            or not isinstance(forcing['rows_sha256'], str)
            or re.fullmatch('[0-9a-f]{64}', forcing['rows_sha256']) is None
            or not utc(forcing['issued_at']) <= utc(forcing['captured_at']) <= origin
            or origin-utc(forcing['issued_at']) > MAX_ISSUE_AGE):
        raise ValueError('forecast was not available at origin')
    rows = forcing['rows']
    if (not isinstance(rows, list) or len(rows) != len(times)
            or any(not isinstance(row, dict) or set(row) !=
                {'at', 'tempF', 'radiationWm2', 'windMph', 'weatherCode'}
                or utc(row['at']) != at for row, at in zip(rows, times))):
        raise ValueError('complete hourly forecast bracket required')
    for row in rows:
        if set(row) != {'at', 'tempF', 'radiationWm2', 'windMph', 'weatherCode'}:
            raise ValueError('unexpected hourly forecast fields')
        values = [row[key] for key in ('tempF', 'radiationWm2', 'windMph', 'weatherCode')]
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or not -40 <= row['tempF'] <= 140 or not 0 <= row['radiationWm2'] <= 1600
                or row['windMph'] < 0):
            raise ValueError('invalid hourly forecast forcing')
    return rows, times


def _from_inputs(artifact, inputs, *, runtime_root=None):
    artifact = validate_artifact(artifact, runtime_root=runtime_root)
    if not isinstance(inputs, dict) or set(inputs) != {'origin', 'horizon_hours', 'forecast', 'actions', 'current', 'mass_history'}:
        raise ValueError('closed split-airflow input contract required')
    origin = utc(inputs['origin']); horizon = inputs['horizon_hours']
    _window(origin, horizon)
    if origin.minute % 5 or origin.second or origin.microsecond:
        raise ValueError('forecast origin must align to five minutes')
    if not utc(artifact['created_at']) <= origin or origin-utc(artifact['trained_through']) > timedelta(hours=26):
        raise ValueError('artifact is future or training is stale')
    actions = deepcopy(inputs['actions'])
    actions['origin'] = utc(actions['origin'])
    for event in [*actions['actions'].values(), actions['mode']]:
        if event is not None:
            for key in ('effective_at', 'received_at', 'created_at'):
                event[key] = utc(event[key])
    states = _states(actions, origin)
    current = {}
    if not isinstance(inputs['current'], dict) or set(inputs['current']) != {'air', 'mass', 'outdoor'}:
        raise ValueError('closed origin receipt roles required')
    for name in ('air', 'mass', 'outdoor'):
        receipt = deepcopy(inputs['current'][name])
        for key in ('receivedAt', 'storedAt', 'validUntil'):
            receipt[key] = utc(receipt[key])
        _validate_receipt(receipt, origin)
        current[name] = receipt
    history = inputs['mass_history']
    lookback = MASS_INITIALIZATION['lookback_minutes']
    expected = [origin-timedelta(minutes=lookback)+i*STEP for i in range(lookback//5+1)]
    if not isinstance(history, list) or len(history) != len(expected) or any(set(row) != {'at', 'receipt'} or utc(row['at']) != at
            for row, at in zip(history, expected)):
        raise ValueError('complete qualified mass-observer history required')
    alpha = 1.0-math.exp(-5/MASS_INITIALIZATION['tau_minutes'])
    latent = None
    for row, at in zip(history, expected):
        receipt = deepcopy(row['receipt'])
        for key in ('receivedAt', 'storedAt', 'validUntil'):
            receipt[key] = utc(receipt[key])
        _validate_receipt(receipt, at)
        latent = receipt['temperatureF'] if latent is None else latent + alpha*(receipt['temperatureF']-latent)
    if receipt != current['mass']:
        raise ValueError('mass-observer endpoint differs from current receipt')
    initial = {'air_f': current['air']['temperatureF'], 'mass_f': latent}
    hourly, times = _hourly(inputs['forecast'], origin, horizon)
    forcings = []
    for step in range(1, horizon*12+1):
        at = origin+step*STEP
        index = min(int((at-times[0]).total_seconds()//3600), len(hourly)-2)
        weight = (at-times[index]).total_seconds()/3600
        left, right = hourly[index], hourly[index+1]
        forcing = {'at': at, 'outdoor_f': left['tempF']+weight*(right['tempF']-left['tempF']),
            'radiation_wm2': left['radiationWm2']+weight*(right['radiationWm2']-left['radiationWm2']), **states}
        features = forcing_features(forcing)
        if any(features[name] != 0 for name in artifact['fit']['inactive_forcing_features']):
            raise ValueError('forecast activates unidentified split-airflow forcing')
        forcings.append(forcing)
    model = AirflowSeed(**artifact['fit']['dynamics'])
    predictions = simulate_airflow(model, initial, forcings)
    trajectory = [{'at': utc(row['at']).isoformat(), **state} for row, state in zip(forcings, predictions)]
    return {'schema': SCHEMA, 'status': 'shadow_candidate', 'origin': origin.isoformat(),
        'horizon_hours': horizon, 'artifact_sha256': artifact_digest(artifact),
        'runtime_sha256': artifact['runtime']['sha256'], 'control_enabled': False,
        'action_assumption': 'qualified_origin_states_held_not_future_confirmation',
        'initial': {**initial, 'north_wall_f': current['mass']['temperatureF']},
        'states': states, 'trajectory': trajectory}


def forecast_at_origin(artifact, origin, *, horizon_hours, forecast_reader,
                       temperature_reader, action_reader, runtime_root=None):
    """Read origin-qualified inputs and return a non-actuating scenario/capture.

    Reader qualification and genuine household evidence remain release gates.
    No missing opening state is inferred from vent or a seasonal schedule.
    """
    origin = utc(origin)
    validate_artifact(artifact, runtime_root=runtime_root)
    # Existing assembler checks exact weather brackets and source receipts.
    current_receipts = {}
    def temperatures(**kwargs):
        rows = temperature_reader(**kwargs)
        role = {'indoor': 'air', 'north_wall': 'mass', 'outdoor': 'outdoor'}[kwargs['stream']]
        if rows and rows[0][1] is not None:
            current_receipts[role] = rows[0][1]
        return rows
    assembled = assemble_origin(origin, horizon_hours=horizon_hours,
        forecast_reader=forecast_reader, temperature_reader=temperatures, action_reader=action_reader)
    if assembled['status'] != 'available':
        return assembled
    if assembled['action_snapshot'] is None:
        return {'status': 'unavailable', 'reason': 'split_action_snapshot_unavailable', 'origin': origin}
    try:
        _states(assembled['action_snapshot'], origin)
    except ValueError as error:
        return {'status': 'unavailable', 'reason': str(error), 'origin': origin}
    targets = [origin-timedelta(minutes=MASS_INITIALIZATION['lookback_minutes'])+i*STEP
               for i in range(MASS_INITIALIZATION['lookback_minutes']//5+1)]
    rows = temperature_reader(stream='north_wall', targets=targets, assessed_at=origin)
    if (len(rows) != len(targets) or any(at != target or receipt is None
            for (at, receipt), target in zip(rows, targets))):
        return {'status': 'unavailable', 'reason': 'mass_observer_history_unavailable', 'origin': origin}
    inputs = {'origin': origin, 'horizon_hours': horizon_hours, 'forecast': assembled['forecast'],
        'actions': assembled['action_snapshot'], 'current': current_receipts,
        'mass_history': [{'at': at, 'receipt': receipt} for at, receipt in rows]}
    output = _from_inputs(artifact, inputs, runtime_root=runtime_root)
    capture = {'schema': CAPTURE_SCHEMA, 'artifact': artifact, 'inputs': inputs, 'output': output}
    capture['sha256'] = sha256(canonical(capture)).hexdigest()
    if len(canonical(capture)) > 1_000_000:
        raise ValueError('split-airflow replay capture exceeds bound')
    return {'status': 'available', 'output': output, 'capture': capture}


def replay_capture(capture, *, runtime_root=None):
    if (not isinstance(capture, dict) or set(capture) != {'schema', 'artifact', 'inputs', 'output', 'sha256'}
            or capture['schema'] != CAPTURE_SCHEMA):
        raise ValueError('invalid split-airflow replay capture')
    core = {k: v for k, v in capture.items() if k != 'sha256'}
    if len(canonical(capture)) > 1_000_000 or sha256(canonical(core)).hexdigest() != capture['sha256']:
        raise ValueError('split-airflow replay digest mismatch')
    output = _from_inputs(capture['artifact'], capture['inputs'], runtime_root=runtime_root)
    if canonical(output) != canonical(capture['output']):
        raise ValueError('split-airflow replay differs from captured output')
    return output
