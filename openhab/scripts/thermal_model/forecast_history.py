"""Origin-time weather forcing from immutable archived forecast snapshots.

This reader only selects information captured by the requested origin. It does
not score a model, infer actions, publish advice, or use observed future weather.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite

SOURCE = 'open_meteo_openhab'
METRICS = ('temperature_f', 'radiation_wm2', 'wind_mph', 'weather_code')
HOUR = timedelta(hours=1)
MAX_ISSUE_AGE = timedelta(hours=6)
MAX_ROWS = 4000


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware forecast timestamp required')
    return value.astimezone(timezone.utc)


def _window(origin, horizon_hours):
    origin = _utc(origin)
    if type(horizon_hours) is not int or not 1 <= horizon_hours <= 72:
        raise ValueError('forecast horizon must be 1 through 72 hours')
    first = origin.replace(minute=0, second=0, microsecond=0)
    target = origin + timedelta(hours=horizon_hours)
    last = target.replace(minute=0, second=0, microsecond=0)
    if last < target:
        last += HOUR
    return origin, tuple(first + i * HOUR for i in range(int((last - first) / HOUR) + 1))


def select_origin_forecast(records, *, origin, horizon_hours):
    return _select_origin_forecast(records, origin=origin, horizon_hours=horizon_hours, retain_receipts=False)


def select_origin_forecast_with_receipts(records, *, origin, horizon_hours):
    return _select_origin_forecast(records, origin=origin, horizon_hours=horizon_hours, retain_receipts=True)


def _select_origin_forecast(records, *, origin, horizon_hours, retain_receipts):
    """Select one complete issuance; late captures and partial issues cannot leak."""
    origin, targets = _window(origin, horizon_hours)
    target_set = set(targets)
    by_issue = {}
    for issued_at, captured_at, valid_for, metric, value in records:
        issued_at, captured_at, valid_for = map(_utc, (issued_at, captured_at, valid_for))
        if metric not in METRICS or valid_for not in target_set:
            raise ValueError('unexpected forecast metric or target')
        if issued_at > origin or captured_at > origin or origin - issued_at > MAX_ISSUE_AGE:
            continue
        if value is not None and (type(value) not in (int, float) or not isfinite(value)):
            raise ValueError('forecast value must be finite numeric or null')
        by_target = by_issue.setdefault(issued_at, {})
        values = by_target.setdefault(valid_for, {})
        if metric in values:
            raise ValueError('duplicate archived forecast metric')
        values[metric] = (value, captured_at)

    for issued_at in sorted(by_issue, reverse=True):
        by_target = by_issue[issued_at]
        if any(set(by_target.get(at, {})) != set(METRICS)
               or any(by_target[at][metric][0] is None for metric in METRICS)
               for at in targets):
            continue
        rows = []
        digest_rows = []
        captured_at = issued_at
        for at in targets:
            values = by_target[at]
            captured_at = max(captured_at, *(record[1] for record in values.values()))
            row = {'at': at, 'tempF': values['temperature_f'][0],
                   'radiationWm2': values['radiation_wm2'][0],
                   'windMph': values['wind_mph'][0],
                   'weatherCode': values['weather_code'][0]}
            rows.append(row)
            digest_rows.append([at.isoformat(), *(
                [metric, values[metric][0], values[metric][1].isoformat()]
                for metric in METRICS)])
        digest = hashlib.sha256(json.dumps(digest_rows, separators=(',', ':'),
            allow_nan=False).encode()).hexdigest()
        selected = {'source': SOURCE, 'issued_at': issued_at, 'captured_at': captured_at,
                    'origin': origin, 'horizon_hours': horizon_hours,
                    'rows_sha256': digest, 'rows': rows}
        if retain_receipts:
            selected.update(schema='earthship-thermal-archived-forecast/v2',
                metric_receipts=[[issued_at, by_target[at][metric][1], at,
                    metric, by_target[at][metric][0]] for at in targets for metric in METRICS])
        return selected
    return None


def fetch_origin_forecast(connection_factory, *, origin, horizon_hours):
    return _fetch_origin_forecast(connection_factory, origin=origin,
                                 horizon_hours=horizon_hours, retain_receipts=False)


def fetch_origin_forecast_with_receipts(connection_factory, *, origin, horizon_hours):
    return _fetch_origin_forecast(connection_factory, origin=origin,
                                 horizon_hours=horizon_hours, retain_receipts=True)


def fetch_pending_origin_forecast_with_receipts(connection_factory, *, origin, horizon_hours, available_by):
    """Read a pending issue from weather already captured before collection."""
    return _fetch_origin_forecast(connection_factory,origin=origin,horizon_hours=horizon_hours,
        retain_receipts=True,available_by=available_by)


def _fetch_origin_forecast(connection_factory, *, origin, horizon_hours, retain_receipts, available_by=None):
    """Use one bounded read-only snapshot of the archived Solar-PV forecast table."""
    origin, targets = _window(origin, horizon_hours)
    known=origin if available_by is None else _utc(available_by)
    if known>origin:raise ValueError('weather knowledge cannot follow pending issue')
    connection = connection_factory()
    try:
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '3000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only transaction required')
            cursor.execute('''SELECT issued_at, captured_at, valid_for, metric, value
                FROM energy_analytics.forecast_snapshots
                WHERE source = %s AND issued_at <= %s AND issued_at >= %s
                  AND captured_at <= %s AND valid_for >= %s AND valid_for <= %s
                  AND metric = ANY(%s)
                ORDER BY issued_at DESC, valid_for, metric LIMIT %s''',
                (SOURCE, known, origin - MAX_ISSUE_AGE, known,
                 targets[0], targets[-1], list(METRICS), MAX_ROWS + 1))
            records = cursor.fetchall()
        if len(records) > MAX_ROWS:
            raise ValueError('archived forecast row bound exceeded')
        if available_by is not None:
            records=[row for row in records if _utc(row[0])<=known and _utc(row[1])<=known]
        return _select_origin_forecast(records, origin=origin, horizon_hours=horizon_hours, retain_receipts=retain_receipts)
    finally:
        connection.close()



def verify_origin_forecast_receipts(forecast):
    """Reconstruct the original metric/capture-clock archive digest, no SQL."""
    from .forcing_capture import _canonical
    from .graduation_policy import _utc as clock
    fields={'schema','source','issued_at','captured_at','origin','horizon_hours',
            'rows_sha256','rows','metric_receipts'}
    if (not isinstance(forecast,dict) or set(forecast)!=fields or
            forecast['schema']!='earthship-thermal-archived-forecast/v2' or
            not isinstance(forecast['metric_receipts'],list)):
        raise ValueError('closed original archived forecast receipts required')
    origin,targets=_window(clock(forecast['origin']),forecast['horizon_hours'])
    rows=forecast['metric_receipts']
    if len(rows)!=len(targets)*len(METRICS) or len(rows)>MAX_ROWS:
        raise ValueError('complete bounded original forecast receipts required')
    records=[];issued=clock(forecast['issued_at'])
    for row in rows:
        if not isinstance(row,list) or len(row)!=5:
            raise ValueError('original archived metric receipt required')
        issue,captured,target=map(clock,row[:3])
        if issue!=issued or not issue<=captured<=origin:
            raise ValueError('mixed or unavailable original archive receipt')
        records.append((issue,captured,target,row[3],row[4]))
    expected=select_origin_forecast_with_receipts(records,origin=origin,horizon_hours=forecast['horizon_hours'])
    if expected is None or _canonical(expected)!=_canonical(forecast):
        raise ValueError('selected weather or archive digest differs from original receipts')
    return forecast
