"""Default-unwired, read-only JDBC acquisition for the separate Dooya v2 family.

Callers must supply one private commissioned profile, eight exact distinct Item
names (including a real provider_status collector Item), and a new dedicated
connection. There is no DSN default/fallback, installation, collector, writer,
forecast/model registration, policy preference input, or actuator path here.
Original schema-v1 readers remain separate for their original producer/replay.
"""
import re

from .shade_observations_v2 import (ITEM_ROLES, MAX_ROWS, MAX_VALUE_BYTES, _utc, _window,
    join_change_only_shade_rows_v2, qualified_shade_intervals_v2, validate_profile_v2)

ITEM_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,99}\Z')


class ShadeHistoryV2Unavailable(RuntimeError):
    """No received-report continuity is inferred from a failed acquisition."""


def fetch_shade_intervals_v2(connection_factory, *, items, profile, start, end, as_of):
    """Acquire bounded original histories inside one read-only repeatable snapshot.

    Missing/ambiguous mappings, duplicate source times, query errors or bound
    violations refuse the complete read. Missing provider-status *history*
    withholds all usable intervals while keeping separately labeled original
    Report observations; no missing role is substituted with ONLINE/ON.
    """
    connection = None
    try:
        start,end = _window(start,end,as_of)
        as_of = _utc(as_of)
        profile = validate_profile_v2(profile)
        if (type(items) is not dict or set(items) != set(ITEM_ROLES)
                or any(type(name) is not str or ITEM_NAME.fullmatch(name) is None
                       for name in items.values())
                or len(set(items.values())) != len(ITEM_ROLES)
                or not callable(connection_factory)):
            raise ValueError('eight distinct exact commissioned v2 Item roles required')
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle v2 history connection required')
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        streams = {}
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '2000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only v2 snapshot required')
            cursor.execute('SHOW transaction_isolation')
            if cursor.fetchone() != ('repeatable read',):
                raise ValueError('repeatable v2 snapshot required')
            table_ids = {}
            for role in ITEM_ROLES:
                cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(items[role],))
                matches = cursor.fetchall()
                if (len(matches) != 1 or type(matches[0][0]) is not int
                        or not 0 <= matches[0][0] <= 2147483647):
                    raise ValueError('unique exact v2 Item mapping required')
                table_ids[role] = matches[0][0]
            if len(set(table_ids.values())) != len(ITEM_ROLES):
                raise ValueError('v2 Item roles share persistence identity')
            total = 0
            for role in ITEM_ROLES:
                table = f'public.item{table_ids[role]:04d}'
                value = (f'CASE WHEN octet_length(value::text) <= {MAX_VALUE_BYTES} '
                         'THEN value::text ELSE NULL END')
                cursor.execute(f'SELECT time, {value} FROM {table} '
                    'WHERE time < %s ORDER BY time DESC LIMIT 1',(start,))
                carry = cursor.fetchone()
                cursor.execute(f'SELECT time, {value} FROM {table} '
                    'WHERE time >= %s AND time < %s ORDER BY time LIMIT 10001',(start,end))
                rows = cursor.fetchall()
                total += len(rows)+int(carry is not None)
                if total > MAX_ROWS:
                    raise ValueError('v2 history row bound exceeded')
                if carry is not None and _utc(carry[0]) >= start:
                    raise ValueError('invalid v2 carry boundary')
                if any(not start <= _utc(at) < end for at,_ in rows):
                    raise ValueError('v2 history outside closed as-of window')
                streams[role] = ([{'stored_at':carry[0],'state':carry[1]}] if carry is not None else [])+[
                    {'stored_at':at,'state':raw} for at,raw in rows]
        joined = join_change_only_shade_rows_v2(streams,start=start,end=end)
        return qualified_shade_intervals_v2(joined,profile=profile,start=start,end=end,as_of=as_of)
    except Exception:
        raise ShadeHistoryV2Unavailable('v2 shade history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # Rollback on close; never commit acquired evidence.
            except Exception:
                pass
