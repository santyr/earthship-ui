"""Bounded source-only JDBC reader for one commissioned Dooya shade.

The caller supplies exact diagnostic, availability and position Item names and
a new dedicated PostgreSQL connection factory. No Item mapping, credential,
listener, model input or command is enabled by importing this module.
"""

from datetime import datetime, timezone
import re

from .shade_observations import (MAX_ROWS, MAX_WINDOW,
                                 join_change_only_shade_rows,
                                 qualified_shade_intervals)


ITEM_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,99}\Z')
ITEM_KEYS = frozenset(('diagnostic_state', 'availability', 'scalar_position'))


class ShadeHistoryUnavailable(RuntimeError):
    """No qualified history may be inferred from this read."""


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware shade history time required')
    return value.astimezone(timezone.utc)


def fetch_shade_intervals(connection_factory, *, items, start, end, as_of):
    """Read one elapsed two-day-or-shorter window without future-origin rows.

    Three Items share one repeatable-read snapshot. An ambiguous/missing Item,
    absent source row, duplicate timestamp, oversized value or failed query
    refuses the whole read instead of returning partial or synthetic coverage.
    """
    connection = None
    try:
        start, end, as_of = map(_utc, (start, end, as_of))
        if not start < end <= as_of or end - start > MAX_WINDOW:
            raise ValueError('bounded elapsed shade window required')
        if (not isinstance(items, dict) or set(items) != ITEM_KEYS
                or any(not isinstance(name, str) or not ITEM_NAME.fullmatch(name)
                       for name in items.values())
                or len(set(items.values())) != 3):
            raise ValueError('three distinct exact shade Item names required')
        if not callable(connection_factory):
            raise ValueError('dedicated connection factory required')
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False,
                               isolation_level='REPEATABLE READ')
        streams = {}
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '2000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only transaction required')
            cursor.execute('SHOW transaction_isolation')
            if cursor.fetchone() != ('repeatable read',):
                raise ValueError('stable snapshot required')
            table_ids = {}
            for key in ('diagnostic_state', 'availability', 'scalar_position'):
                cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',
                               (items[key],))
                matches = cursor.fetchall()
                if (len(matches) != 1 or type(matches[0][0]) is not int
                        or not 0 <= matches[0][0] <= 2147483647):
                    raise ValueError('unique shade Item mapping required')
                table_ids[key] = matches[0][0]
            if len(set(table_ids.values())) != 3:
                raise ValueError('shade Items share a persistence table')
            total = 0
            for key in ('diagnostic_state', 'availability', 'scalar_position'):
                table = f'public.item{table_ids[key]:04d}'
                value = ('CASE WHEN octet_length(value::text) <= 8192 '
                         'THEN value::text ELSE NULL END')
                cursor.execute(f'SELECT time, {value} FROM {table} '
                               'WHERE time < %s ORDER BY time DESC LIMIT 1', (start,))
                carry = cursor.fetchone()
                cursor.execute(f'SELECT time, {value} FROM {table} '
                               'WHERE time >= %s AND time < %s ORDER BY time LIMIT 10001',
                               (start, end))
                rows = cursor.fetchall()
                total += len(rows) + int(carry is not None)
                if total > MAX_ROWS:
                    raise ValueError('shade row bound exceeded')
                if carry is not None and _utc(carry[0]) >= start:
                    raise ValueError('invalid shade carry boundary')
                if any(not start <= _utc(at) < end for at, _ in rows):
                    raise ValueError('shade history outside window')
                streams[key] = ([dict(stored_at=carry[0], state=carry[1])]
                                if carry is not None else []) + [
                                    dict(stored_at=at, state=raw) for at, raw in rows]
        joined = join_change_only_shade_rows(
            streams['diagnostic_state'], streams['availability'],
            streams['scalar_position'], start=start, end=end,
        )
        return qualified_shade_intervals(joined, start=start, end=end)
    except Exception:
        raise ShadeHistoryUnavailable('shade history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; never commit
            except Exception:
                pass
