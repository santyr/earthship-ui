"""Assemble captured weather and receipt-qualified initial states at one origin."""

from datetime import datetime, timezone

from .forecast_history import SOURCE, _window
from .temperature_history import STREAMS, _validate_receipt


def assemble_origin(origin, *, horizon_hours, forecast_reader, temperature_reader):
    """Return observed-at-origin inputs only; no model score or action authority."""
    at, targets = _window(origin, horizon_hours)
    if at.second or at.microsecond or at.minute % 5:
        raise ValueError('origin must align to five minutes')
    forecast = forecast_reader(origin=at, horizon_hours=horizon_hours)
    if forecast is None:
        return {'status': 'unavailable', 'reason': 'forecast_unavailable', 'origin': at}
    if (forecast['source'] != SOURCE or forecast['origin'] != at
            or forecast['horizon_hours'] != horizon_hours
            or forecast['issued_at'] > at or forecast['captured_at'] > at):
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
    return {'status': 'available', 'origin': at, 'horizon_hours': horizon_hours,
            'initial': current, 'receipts': receipts, 'forecast': forecast,
            'action_knowledge': 'not_qualified'}
