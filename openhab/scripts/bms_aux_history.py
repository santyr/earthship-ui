"""Exact, bounded, read-only JDBC transport for Discover BMS aux evidence.

Importing this module connects to no database and changes no quality flag.
Callers must supply a dedicated restricted connection and reviewed cutover.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from bms_aux_evidence import ITEM, MAX_BYTES, MAX_ROWS, TTL, qualify_bms_aux_day


class BmsAuxDayHistoryUnavailable(RuntimeError):
    """No auxiliary daily quality may be inferred from this database read."""


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware BMS auxiliary history time required')
    return value.astimezone(timezone.utc)


def fetch_qualified_bms_aux_day(connection_factory, *, local_date, as_of, cutover,
                                site_timezone='America/Denver'):
    """Read the exact Item in one bounded repeatable-read transaction."""
    connection = None
    try:
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise ValueError('local_date must be a date')
        if not callable(connection_factory):
            raise ValueError('dedicated connection factory required')
        zone = ZoneInfo(site_timezone)
        start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        as_of, cutover = _utc(as_of), _utc(cutover)
        if not cutover <= start < end <= as_of:
            raise ValueError('auxiliary day precedes cutover or is incomplete')
        connection = connection_factory()
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False,
                               isolation_level='REPEATABLE READ')
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
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',
                           (ITEM,))
            matches = cursor.fetchall()
            if (len(matches) != 1 or type(matches[0][0]) is not int
                    or not 0 <= matches[0][0] <= 2147483647):
                raise ValueError('unique auxiliary Item mapping required')
            table = f'public.item{matches[0][0]:04d}'
            value = (f'CASE WHEN octet_length(value::text) <= {MAX_BYTES} '
                     'THEN value::text ELSE NULL END')
            cursor.execute(f'SELECT time, {value} FROM {table} '
                           f'WHERE time >= %s AND time < %s ORDER BY time LIMIT {MAX_ROWS + 1}',
                           (start - TTL, end))
            rows = cursor.fetchall()
            if len(rows) > MAX_ROWS:
                raise ValueError('auxiliary row budget exceeded')
        return qualify_bms_aux_day(local_date, as_of=as_of, cutover=cutover,
                                   observations=rows, site_timezone=site_timezone)
    except Exception:
        raise BmsAuxDayHistoryUnavailable('BMS auxiliary day history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; never commit
            except Exception:
                pass
