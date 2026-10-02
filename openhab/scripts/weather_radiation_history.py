"""Dedicated bounded SELECT-only JDBC transport; no activation or credentials.

Caller supplies a new restricted connection and independently reviewed cutover.
Importing this module does not collect, publish, train or contact PostgreSQL.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from weather_radiation_evidence import RadiationPolicy
from weather_radiation_reader import MAX_BYTES, MAX_ROWS, _utc, _validate, select_radiation_at, select_radiation_window

ITEM = 'Weather_Radiation_Evidence_JSON'


class RadiationHistoryUnavailable(RuntimeError):
    pass


def _fetch(connection_factory, start, end):
    connection = None
    try:
        if not callable(connection_factory):
            raise ValueError('explicit dedicated connection factory required')
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='2000ms'")
            cursor.execute("SET LOCAL lock_timeout='1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout='5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only transaction required')
            cursor.execute('SHOW transaction_isolation')
            if cursor.fetchone() != ('repeatable read',):
                raise ValueError('stable snapshot required')
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,))
            matches = cursor.fetchall()
            if (len(matches) != 1 or type(matches[0][0]) is not int
                    or not 0 <= matches[0][0] <= 2147483647):
                raise ValueError('unique radiation Item mapping required')
            table = f'public.item{matches[0][0]:04d}'
            value = f'CASE WHEN octet_length(value::text) <= {MAX_BYTES} THEN value::text ELSE NULL END'
            cursor.execute(f'SELECT time, {value} FROM {table} WHERE time < %s ORDER BY time DESC LIMIT 1', (start,))
            carry = cursor.fetchone()
            cursor.execute(f'SELECT time, {value} FROM {table} WHERE time >= %s AND time <= %s ORDER BY time LIMIT {MAX_ROWS + 1}', (start, end))
            rows = cursor.fetchall()
        if (len(rows) + (carry is not None) > MAX_ROWS
                or carry is not None and _utc(carry[0]) >= start
                or any(not start <= _utc(at) <= end for at, _ in rows)):
            raise ValueError('complete bounded history contract failed')
        return ([] if carry is None else [carry]) + rows
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; never commit or write
            except Exception:
                pass


def fetch_radiation_at(connection_factory, *, target, assessed_at, cutover, policy):
    try:
        if not isinstance(policy, RadiationPolicy):
            raise ValueError('explicit radiation policy required')
        target = _utc(target)
        history = target - timedelta(seconds=policy.validity_seconds)
        kwargs = dict(target=target, assessed_at=assessed_at, history_start=history, cutover=cutover, policy=policy)
        _validate(start=target, end=target, assessed_at=assessed_at, history_start=history, cutover=cutover, policy=policy)
        return select_radiation_at(_fetch(connection_factory, history, target), **kwargs)
    except Exception:
        raise RadiationHistoryUnavailable('radiation history unavailable') from None


def fetch_radiation_window(connection_factory, *, start, end, assessed_at, cutover, policy):
    try:
        if not isinstance(policy, RadiationPolicy):
            raise ValueError('explicit radiation policy required')
        start, end = _utc(start), _utc(end)
        history = start - timedelta(seconds=policy.validity_seconds)
        kwargs = dict(start=start, end=end, assessed_at=assessed_at, history_start=history, cutover=cutover, policy=policy)
        select_radiation_window([], **kwargs)  # Validate before opening PostgreSQL.
        fetch_end = min(_utc(assessed_at), end + timedelta(seconds=policy.validity_seconds))
        result = select_radiation_window(_fetch(connection_factory, history, fetch_end), **kwargs)
        return {**result, 'source_item': ITEM, 'source_cutover': _utc(cutover).isoformat()}
    except Exception:
        raise RadiationHistoryUnavailable('radiation history unavailable') from None


def fetch_radiation_day(connection_factory, *, local_date, as_of, cutover, policy,
                        site_timezone='America/Denver'):
    try:
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise ValueError('local date required')
        zone = ZoneInfo(site_timezone)
        start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        result = fetch_radiation_window(connection_factory, start=start, end=end,
            assessed_at=as_of, cutover=cutover, policy=policy)
        return {**result, 'local_date': local_date.isoformat(), 'site_timezone': site_timezone}
    except Exception:
        raise RadiationHistoryUnavailable('radiation history unavailable') from None
