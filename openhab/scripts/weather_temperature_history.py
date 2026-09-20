"""Bounded, read-only JDBC fetch for elapsed temperature targets.

connection_factory must return a NEW dedicated psycopg2 connection with a
bounded connect timeout. This module never reads credentials or falls back to
another Item. No production caller or Item is installed by importing it.
"""
from datetime import timedelta

from weather_temperature_evidence import TemperaturePolicy
from weather_temperature_reader import _utc, select_temperature_grid

EVIDENCE_ITEM = 'Weather_Temperature_Evidence_JSON'


class TemperatureHistoryUnavailable(RuntimeError):
    pass


def fetch_temperature_target(connection_factory, *, target, assessed_at, stream, policy):
    return fetch_temperature_grid(connection_factory, targets=[target], assessed_at=assessed_at,
                                  stream=stream, policy=policy)[0][1]


def fetch_temperature_grid(connection_factory, *, targets, assessed_at, stream, policy):
    """Fetch one bounded elapsed-day grid using one dedicated stable snapshot.

    Preserves original source timestamps and qualification metadata. This is a
    reader only: callers must explicitly decide how unqualified targets affect
    training; never interpolate them into apparently healthy measurements.
    """
    connection = None
    try:
        if not isinstance(policy, TemperaturePolicy): raise ValueError('explicit policy required')
        if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= 289:
            raise ValueError('bounded target grid required')
        targets = [_utc(target) for target in targets]
        assessed_at = _utc(assessed_at)
        start = targets[0] - timedelta(seconds=policy.validity_seconds)
        target = targets[-1]
        select_temperature_grid([], targets=targets, assessed_at=assessed_at,
                                history_start=start, stream=stream, policy=policy)
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '2000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',): raise ValueError('read-only transaction required')
            cursor.execute('SHOW transaction_isolation')
            if cursor.fetchone() != ('repeatable read',): raise ValueError('stable snapshot required')
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (EVIDENCE_ITEM,))
            matches = cursor.fetchall()
            if len(matches) != 1 or type(matches[0][0]) is not int or not 0 <= matches[0][0] <= 2147483647:
                raise ValueError('unique evidence Item mapping required')
            # The only interpolated identifier is derived from a validated int.
            table = f'public.item{matches[0][0]:04d}'
            value = 'CASE WHEN octet_length(value::text) <= 8192 THEN value::text ELSE NULL END'
            cursor.execute(f'SELECT time, {value} FROM {table} WHERE time < %s ORDER BY time DESC LIMIT 1', (start,))
            carry = cursor.fetchone()
            cursor.execute(f'SELECT time, {value} FROM {table} WHERE time >= %s AND time <= %s ORDER BY time LIMIT 10001', (start, target))
            rows = cursor.fetchall()
        observations = ([] if carry is None else [carry]) + rows
        if len(observations) > 10000: raise ValueError('history row bound exceeded')
        if carry is not None and _utc(carry[0]) >= start: raise ValueError('invalid carry boundary')
        if any(not start <= _utc(at) <= target for at, _raw in rows): raise ValueError('history outside window')
        # Oversized/NULL raw values remain barriers. Never silently drop them.
        return select_temperature_grid(observations, targets=targets, assessed_at=assessed_at,
                                       history_start=start, stream=stream, policy=policy)
    except Exception:
        raise TemperatureHistoryUnavailable('temperature evidence history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; no commit or write path
            except Exception:
                pass
