"""Assemble captured weather and receipt-qualified initial states at one origin."""

from datetime import datetime, timedelta, timezone
from math import isfinite
import re

from .forecast_history import SOURCE, _utc, _window
from .schema import ACTION_KINDS, SOURCE_WEIGHTS
from .temperature_history import STREAMS, _validate_receipt


def _validate_actions(snapshot, at):
    if (not isinstance(snapshot, dict) or
            set(snapshot) != {'source', 'origin', 'actions', 'mode', 'missing_actions', 'status'} or
            snapshot['source'] != 'thermal_intel_append_only_journal' or
            snapshot['origin'] != at or
            snapshot['status'] != 'as_of_snapshot_not_outcome_confirmation' or
            not isinstance(snapshot['actions'], dict) or
            not set(snapshot['actions']) <= set(ACTION_KINDS) or
            snapshot['missing_actions'] != sorted(set(ACTION_KINDS) - set(snapshot['actions']))):
        raise ValueError('invalid origin-time action snapshot')
    for event in [*snapshot['actions'].values(), snapshot['mode']]:
        if event is None:
            continue
        if (not isinstance(event, dict) or set(event) != {
                'state', 'source', 'confidence', 'effective_at', 'received_at',
                'created_at', 'event_id'} or event['source'] not in SOURCE_WEIGHTS or
                any(event.get(key) is None for key in
                    ('effective_at', 'received_at', 'created_at'))):
            raise ValueError('action knowledge is not available at origin')
        effective, received, created = (_utc(event[key]) for key in
                                        ('effective_at', 'received_at', 'created_at'))
        if not effective <= received <= created <= at:
            raise ValueError('action knowledge is not available at origin')


def assemble_origin(origin, *, horizon_hours, forecast_reader, temperature_reader,
                    action_reader=None):
    """Return observed-at-origin inputs only; no model score or action authority."""
    at, targets = _window(origin, horizon_hours)
    if at.second or at.microsecond or at.minute % 5:
        raise ValueError('origin must align to five minutes')
    forecast = forecast_reader(origin=at, horizon_hours=horizon_hours)
    if forecast is None:
        return {'status': 'unavailable', 'reason': 'forecast_unavailable', 'origin': at}
    if (forecast['source'] != SOURCE or forecast['origin'] != at
            or forecast['horizon_hours'] != horizon_hours
            or forecast['issued_at'] > at or forecast['captured_at'] > at
            or not isinstance(forecast.get('rows_sha256'), str)
            or re.fullmatch('[0-9a-f]{64}', forecast['rows_sha256']) is None):
        raise ValueError('forecast is not available at origin')
    rows = forecast.get('rows')
    if (not isinstance(rows, list) or len(rows) != len(targets)
            or any(not isinstance(row, dict) or row.get('at') != target
                   or set(row) != {'at', 'tempF', 'radiationWm2', 'windMph', 'weatherCode'}
                   for row, target in zip(rows, targets))):
        raise ValueError('forecast hourly bracket is incomplete')
    current = {}
    receipts = {}
    for role, (stream, _, _) in STREAMS.items():
        rows = temperature_reader(stream=stream, targets=[at], assessed_at=at)
        if not isinstance(rows, list) or len(rows) != 1 or rows[0][0] != at:
            raise ValueError('temperature reader returned an invalid target')
        receipt = rows[0][1]
        if receipt is None:
            return {'status': 'unavailable', 'reason': role + '_receipt_unavailable',
                    'origin': at}
        _validate_receipt(receipt, at)
        current[role + '_f'] = receipt['temperatureF']
        receipts[role] = {
            'received_at': receipt['receivedAt'].astimezone(timezone.utc),
            'stored_at': receipt['storedAt'].astimezone(timezone.utc),
            'snapshot_sha256': receipt['snapshotSha256'],
        }
    actions = None if action_reader is None else action_reader(origin=at)
    if actions is not None:
        _validate_actions(actions, at)
    return {'status': 'available', 'origin': at, 'horizon_hours': horizon_hours,
            'initial': current, 'receipts': receipts, 'forecast': forecast,
            'action_knowledge': ('not_qualified' if actions is None else
                                 'as_of_snapshot_not_qualified'),
            'action_snapshot': actions}


def pair_persistence_outcome(origin, *, horizon_hours, assessed_at,
                             forecast_reader, temperature_reader, action_reader=None):
    """Score only same-origin air persistence against a qualified later receipt.

    This replay seam does not simulate a physical model, infer action compliance,
    or use future observed weather as origin-time forcing. A target not yet due
    is reported before any reader is called.
    """
    at, _ = _window(origin, horizon_hours)
    if at.second or at.microsecond or at.minute % 5:
        raise ValueError('origin must align to five minutes')
    assessed = _utc(assessed_at)
    target = at + timedelta(hours=horizon_hours)
    if assessed < target:
        return {'status': 'pending', 'origin': at, 'target': target}
    assembled = assemble_origin(at, horizon_hours=horizon_hours,
        forecast_reader=forecast_reader, temperature_reader=temperature_reader,
        action_reader=action_reader)
    if assembled['status'] != 'available':
        return assembled
    stream = STREAMS['air'][0]
    rows = temperature_reader(stream=stream, targets=[target], assessed_at=assessed)
    if not isinstance(rows, list) or len(rows) != 1 or rows[0][0] != target:
        raise ValueError('temperature reader returned an invalid outcome target')
    receipt = rows[0][1]
    if receipt is None:
        return {'status': 'unavailable', 'reason': 'outcome_receipt_unavailable',
                'origin': at, 'target': target}
    _validate_receipt(receipt, target)
    initial = assembled['initial']['air_f']
    observed = receipt['temperatureF']
    if any(type(value) not in (int, float) or not isfinite(value)
           for value in (initial, observed)):
        raise ValueError('nonfinite qualified temperature')
    error = initial - observed
    return {'status': 'paired', 'origin': at, 'target': target,
            'baseline': 'same_origin_air_persistence',
            'initial_air_f': initial, 'observed_air_f': observed,
            'signed_error_f': error, 'absolute_error_f': abs(error),
            'forecast_sha256': assembled['forecast']['rows_sha256'],
            'action_knowledge': assembled['action_knowledge'],
            'outcome_receipt': {
                'received_at': receipt['receivedAt'].astimezone(timezone.utc),
                'stored_at': receipt['storedAt'].astimezone(timezone.utc),
                'snapshot_sha256': receipt['snapshotSha256']}}
