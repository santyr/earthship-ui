"""Bounded, read-only JDBC transport for the future MPPT60 PV evidence Item.

No connection, Item mapping, credential grant or forecast consumer is created
by importing this module. The caller supplies a dedicated connection factory.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from pv_day_evidence import MAX_ROWS, qualify_pv_day


ITEM = 'MPPT60_PV_Day_Evidence_JSON'
MAX_VALUE_BYTES = 4096


class PVDayHistoryUnavailable(RuntimeError):
    """No qualified PV total may be inferred from this database read."""


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware PV history time required')
    return value.astimezone(timezone.utc)


def fetch_qualified_pv_day(connection_factory, *, local_date, as_of, cutover,
                           site_timezone='America/Denver'):
    """Qualify one elapsed local day from the exact source-bound evidence Item.

    The single repeatable-read transaction resolves exactly one Item/table,
    bounds original rows and value size, and never deduplicates or fills gaps.
    A caller must separately qualify the stream activation cutover and use a
    dedicated restricted PostgreSQL role with SELECT on this Item only.
    """
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
            raise ValueError('PV day precedes cutover or is incomplete')
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
                raise ValueError('unique PV evidence Item mapping required')
            table = f'public.item{matches[0][0]:04d}'
            value = (f'CASE WHEN octet_length(value::text) <= {MAX_VALUE_BYTES} '
                     'THEN value::text ELSE NULL END')
            cursor.execute(f'SELECT time, {value} FROM {table} '
                           f'WHERE time >= %s AND time < %s ORDER BY time LIMIT {MAX_ROWS + 1}',
                           (start, end))
            rows = cursor.fetchall()
            if len(rows) > MAX_ROWS:
                raise ValueError('PV evidence row budget exceeded')
        result = qualify_pv_day(local_date, as_of=as_of, observations=rows,
                                site_timezone=site_timezone)
        return {**result, 'source_item': ITEM, 'source_cutover': cutover.isoformat()}
    except Exception:
        raise PVDayHistoryUnavailable('PV day history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; never commit
            except Exception:
                pass
