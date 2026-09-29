"""Exact, bounded, read-only JDBC transport for rain-counter day evidence.

Importing this module does not connect to PostgreSQL or activate collection.
The caller supplies a new dedicated connection through a restricted role.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from weather_rain_day import MAX_BYTES, MAX_ROWS, qualify_rain_day
from weather_rain_day_recovery import qualify_rain_day_recovery
from weather_rain_evidence import RainPolicy


ITEM = 'Weather_Rain_Evidence_JSON'


class RainDayHistoryUnavailable(RuntimeError):
    """No qualified rain total may be inferred from this database read."""


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware rain history timestamp required')
    return value.astimezone(timezone.utc)


def fetch_qualified_rain_day(connection_factory, *, local_date, as_of,
                             cutover, policy, site_timezone='America/Denver'):
    """Production strict v1 reader; never substitutes recovered observations."""
    return _fetch_rain_day(connection_factory, local_date=local_date, as_of=as_of,
                           cutover=cutover, policy=policy, site_timezone=site_timezone,
                           qualifier=qualify_rain_day)


def fetch_candidate_recovered_rain_day(connection_factory, *, local_date,
                                       as_of, cutover, policy,
                                       site_timezone='America/Denver'):
    """Default-off read-only assessor; not called by the forecast worker."""
    return _fetch_rain_day(connection_factory, local_date=local_date, as_of=as_of,
                           cutover=cutover, policy=policy, site_timezone=site_timezone,
                           qualifier=qualify_rain_day_recovery)


def _fetch_rain_day(connection_factory, *, local_date, as_of, cutover, policy,
                    site_timezone, qualifier):
    """Read last pre-day carry and bounded original rows in one stable snapshot.

    A pre-cutover or incomplete day, mapping ambiguity, permission failure,
    NULL/oversized row, gap, restart or boundary uncertainty fails closed.
    The caller must pin a reviewed activation time and dedicated SELECT role.
    """
    connection = None
    try:
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise ValueError('local_date must be a date')
        if not callable(connection_factory) or not isinstance(policy, RainPolicy):
            raise ValueError('connection factory and rain policy required')
        zone = ZoneInfo(site_timezone)
        start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        assessed_at, cutover = _utc(as_of), _utc(cutover)
        if not cutover <= start < end <= assessed_at:
            raise ValueError('rain day precedes cutover or is incomplete')
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
                raise ValueError('unique rain evidence Item mapping required')
            table = f'public.item{matches[0][0]:04d}'
            value = (f'CASE WHEN octet_length(value::text) <= {MAX_BYTES} '
                     'THEN value::text ELSE NULL END')
            cursor.execute(f'SELECT time, {value} FROM {table} '
                           'WHERE time < %s ORDER BY time DESC LIMIT 1', (start,))
            carry = cursor.fetchone()
            cursor.execute(f'SELECT time, {value} FROM {table} '
                           f'WHERE time >= %s AND time <= %s ORDER BY time LIMIT {MAX_ROWS + 1}',
                           (start, end + timedelta(seconds=policy.validity_seconds)))
            rows = cursor.fetchall()
            if len(rows) + (carry is not None) > MAX_ROWS:
                raise ValueError('rain evidence row budget exceeded')
        observations = ([] if carry is None else [carry]) + rows
        result = qualifier(local_date, as_of=assessed_at,
                           observations=observations, policy=policy,
                           site_timezone=site_timezone)
        return {**result, 'source_item': ITEM,
                'source_cutover': cutover.isoformat()}
    except Exception:
        raise RainDayHistoryUnavailable('rain day history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rollback on close; never commit
            except Exception:
                pass
