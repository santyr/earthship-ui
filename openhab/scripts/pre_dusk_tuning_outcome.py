"""Restricted, read-only source-bound completed-night outcome transport.

It reuses Solar_PV's canonical SoC sequence reader and trough assessor. No
held numeric SoC, Item minimum, forecast publication, or action is involved.
"""

from datetime import date, datetime, timedelta, timezone
import math

from advisory_windows import trough_window


ITEM = 'BMS_SOC_Evidence_JSON'
MAX_ROWS = 10001


class OutcomeHistoryUnavailable(ValueError):
    """A completed qualified trough cannot be established."""


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware time required')
    return value.astimezone(timezone.utc)


def read_completed_outcome(connection_factory, *, day, as_of, epoch_start,
                           epoch_end=None, reader=None, assessor=None):
    """Assess one fully elapsed night in one bounded repeatable-read snapshot.

    `epoch_start`/`epoch_end` must be resolved from the physical bank registry
    by the caller. Supplying a different bank boundary must never be inferred
    from a forecast issue or numeric SoC alone.
    """
    connection = None
    try:
        if not callable(connection_factory) or not isinstance(day, date) or isinstance(day, datetime):
            raise ValueError('date and connection required')
        as_of, epoch_start = _utc(as_of), _utc(epoch_start)
        epoch_end = _utc(epoch_end) if epoch_end is not None else None
        window = trough_window(day, 'America/Denver')
        if (as_of < window.end or as_of > datetime.now(timezone.utc) + timedelta(seconds=5)
                or epoch_start > window.start
                or (epoch_end is not None and epoch_end < window.end)):
            raise ValueError('incomplete target or wrong physical bank')
        from earthship_energy.reader import fetch_freshness_observations
        from earthship_energy.trough_assessment import assess_trough_measurement
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
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,))
            matches = cursor.fetchall()
            if (len(matches) != 1 or type(matches[0][0]) is not int
                    or not 0 <= matches[0][0] <= 2147483647):
                raise ValueError('unique atomic SoC Item mapping required')
        table = f'item{matches[0][0]:04d}'
        observations = (reader or fetch_freshness_observations)(
            connection, table, window.start-timedelta(seconds=120), window.end,
            row_limit=MAX_ROWS)
        if not isinstance(observations, list) or len(observations) > MAX_ROWS:
            raise ValueError('bounded original evidence rows required')
        result = (assessor or assess_trough_measurement)(
            prediction_day=day, site_timezone='America/Denver', assessed_at=as_of,
            observations=observations, epoch_start=epoch_start, epoch_end=epoch_end)
        if (not isinstance(result, dict) or result.get('status') != 'measured'
                or result.get('prediction_day') != day.isoformat()
                or result.get('source') != ITEM
                or result.get('assessment_version') != 'atomic-soc-trough-v1'
                or type(result.get('min_soc_pct')) not in (int, float)
                or not math.isfinite(result['min_soc_pct'])
                or not 0 <= result['min_soc_pct'] <= 100
                or type(result.get('coverage')) not in (int, float)
                or not math.isfinite(result['coverage'])
                or not 0.9 <= result['coverage'] <= 1
                or not isinstance(result.get('evidence_digest'), str)
                or len(result['evidence_digest']) != 64):
            raise ValueError('qualified completed-night outcome unavailable')
        return result
    except Exception:
        # Do not expose JDBC credentials, raw source receipts or database errors.
        raise OutcomeHistoryUnavailable('completed-night history unavailable') from None
    finally:
        if connection is not None:
            try:
                connection.close()  # rolls back read-only snapshot
            except Exception:
                pass
